"""Mutation evidence for the tracked-content public-boundary gate."""

from __future__ import annotations

from io import BytesIO
import hashlib
from pathlib import Path
import struct
import subprocess
import zipfile
import zlib

import pytest

from scripts.check_public_boundary import main


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


TEST_NAME = "qvx"
TEST_NAME_DIGEST = hashlib.sha256(TEST_NAME.encode("ascii")).hexdigest()


def _scan(
    root: Path,
    approved_binary_digests: dict[str, str] | None = None,
) -> int:
    kwargs = {"private_name_digest": TEST_NAME_DIGEST}
    if approved_binary_digests is not None:
        kwargs["approved_binary_digests"] = approved_binary_digests
    return main(["--root", str(root)], **kwargs)


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    checksum = zlib.crc32(kind + payload).to_bytes(4, "big")
    return struct.pack(">I", len(payload)) + kind + payload + checksum


def _valid_png_with_text(text: bytes) -> bytes:
    header = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    image = zlib.compress(b"\0\0\0\0")
    return b"\x89PNG\r\n\x1a\n" + b"".join(
        (
            _png_chunk(b"IHDR", header),
            _png_chunk(b"tEXt", b"note\0" + text),
            _png_chunk(b"IDAT", image),
            _png_chunk(b"IEND", b""),
        )
    )


def _valid_png_with_near_miss() -> bytes:
    return _valid_png_with_text(b"QVM\xff")


def _minimal_sfnt(payload: bytes) -> bytes:
    header = b"\x00\x01\x00\x00" + struct.pack(">HHHH", 1, 0, 0, 0)
    directory = b"name" + struct.pack(">III", 0, 28, len(payload))
    return header + directory + payload


@pytest.fixture
def tracked_repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "--quiet")
    return tmp_path


@pytest.mark.parametrize(
    "mutant",
    (
        TEST_NAME.upper(),
        "netbox-" + TEST_NAME,
        TEST_NAME + "-backend",
        TEST_NAME + "-mcp",
        TEST_NAME + "_credential_id",
        TEST_NAME + "-secret:00000000-0000-0000-0000-000000000000",
        f'"{TEST_NAME[0]}" + "{TEST_NAME[1]}" + "{TEST_NAME[2]}"',
        '"".join((' + ", ".join(repr(char) for char in TEST_NAME) + "))",
    ),
)
def test_boundary_rejects_representative_tracked_mutations(
    tracked_repo: Path, mutant: str
) -> None:
    (tracked_repo / "mutant.txt").write_text(mutant, encoding="utf-8")
    _git(tracked_repo, "add", "mutant.txt")
    assert _scan(tracked_repo) == 1


def test_boundary_ignores_only_gitignored_content(tracked_repo: Path) -> None:
    (tracked_repo / "public.txt").write_text("Public Proxbox API", encoding="utf-8")
    (tracked_repo / ".gitignore").write_text("scratch.txt\n", encoding="utf-8")
    _git(tracked_repo, "add", "public.txt", ".gitignore")
    (tracked_repo / "scratch.txt").write_text(TEST_NAME, encoding="utf-8")
    assert _scan(tracked_repo) == 0


def test_boundary_rejects_forbidden_tracked_filename(tracked_repo: Path) -> None:
    forbidden = tracked_repo / f"{TEST_NAME}-backend.txt"
    forbidden.write_text("otherwise public", encoding="utf-8")
    _git(tracked_repo, "add", forbidden.name)
    assert _scan(tracked_repo) == 1


def test_boundary_fails_closed_when_git_enumeration_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_git_enumeration(*args: object, **kwargs: object) -> None:
        del kwargs
        command = args[0] if args else []
        raise subprocess.CalledProcessError(returncode=128, cmd=command)

    monkeypatch.setattr(subprocess, "run", fail_git_enumeration)
    assert _scan(tmp_path) == 2


@pytest.mark.parametrize("mutation_kind", ("multiline", "byte_tuple", "join"))
def test_boundary_rejects_multiline_and_ast_constant_mutations(
    tracked_repo: Path, mutation_kind: str
) -> None:
    fragments = tuple(TEST_NAME)
    if mutation_kind == "multiline":
        source = "PRIVATE = (\n" + " +\n".join(map(repr, fragments)) + "\n)\n"
    elif mutation_kind == "byte_tuple":
        integers = ", ".join(str(part) for part in TEST_NAME.encode("ascii"))
        source = f'PRIVATE = bytes(({integers})).decode("ascii")\n'
    else:
        source = 'PRIVATE = "".join((' + ", ".join(map(repr, fragments)) + "))\n"
    (tracked_repo / "mutant.py").write_text(source, encoding="utf-8")
    _git(tracked_repo, "add", "mutant.py")
    assert _scan(tracked_repo) == 1


def test_boundary_rejects_nul_smuggling(tracked_repo: Path) -> None:
    encoded_name = TEST_NAME.encode("ascii")
    payload = b"\0".join(bytes((part,)) for part in encoded_name)
    (tracked_repo / "mutant.bin").write_bytes(payload)
    _git(tracked_repo, "add", "mutant.bin")
    assert _scan(tracked_repo) == 1


@pytest.mark.parametrize(
    ("payload", "expected"),
    (
        (bytes((255,)) + TEST_NAME.upper().encode("ascii"), 1),
        (bytes((255,)) + b"NMR", 2),
    ),
)
def test_boundary_scans_invalid_utf8_git_objects(
    tracked_repo: Path, payload: bytes, expected: int
) -> None:
    (tracked_repo / "mutant.bin").write_bytes(payload)
    _git(tracked_repo, "add", "mutant.bin")
    assert _scan(tracked_repo) == expected


def test_boundary_rejects_invalid_bytes_hidden_behind_binary_suffix(
    tracked_repo: Path,
) -> None:
    payload = b"\x89PNG\r\n\x1a\n" + bytes((255,)) + TEST_NAME.encode("ascii")
    (tracked_repo / "mutant.png").write_bytes(payload)
    _git(tracked_repo, "add", "mutant.png")
    assert _scan(tracked_repo) == 1


@pytest.mark.parametrize(
    ("member_name", "member_content"),
    (
        ("nested/public.txt", TEST_NAME),
        (f"nested/{TEST_NAME}.txt", "public"),
    ),
)
def test_boundary_inspects_archive_members(
    tracked_repo: Path,
    member_name: str,
    member_content: str,
) -> None:
    payload = BytesIO()
    with zipfile.ZipFile(payload, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(member_name, member_content)
    (tracked_repo / "mutant.zip").write_bytes(payload.getvalue())
    _git(tracked_repo, "add", "mutant.zip")
    assert _scan(tracked_repo) == 1


def test_boundary_allows_valid_binary_near_miss(tracked_repo: Path) -> None:
    payload = _valid_png_with_near_miss()
    (tracked_repo / "public.png").write_bytes(payload)
    _git(tracked_repo, "add", "public.png")
    approved = {"public.png": hashlib.sha256(payload).hexdigest()}
    assert _scan(tracked_repo, approved) == 0


def test_boundary_rejects_unpinned_valid_binary_near_miss(tracked_repo: Path) -> None:
    (tracked_repo / "public.png").write_bytes(_valid_png_with_near_miss())
    _git(tracked_repo, "add", "public.png")
    assert _scan(tracked_repo) == 2


def test_boundary_rejects_changed_digest_pinned_binary(tracked_repo: Path) -> None:
    payload = _valid_png_with_near_miss()
    (tracked_repo / "public.png").write_bytes(payload)
    _git(tracked_repo, "add", "public.png")
    approved = {"public.png": hashlib.sha256(payload + b"changed").hexdigest()}
    assert _scan(tracked_repo, approved) == 2


@pytest.mark.parametrize(
    ("filename", "payload"),
    (
        ("carrier.png", _valid_png_with_text(TEST_NAME.encode("ascii"))),
        (
            "carrier.jpg",
            b"\xff\xd8\xff" + TEST_NAME.encode("ascii") + b"\xff\xd9",
        ),
        ("carrier.gif", b"GIF89a\0" + TEST_NAME.encode("ascii") + b"\0;"),
        ("carrier.ttf", _minimal_sfnt(TEST_NAME.encode("ascii"))),
        (
            "carrier.woff",
            b"wOFF\x00\x01\x00\x00"
            + struct.pack(">I", 12 + len(TEST_NAME))
            + TEST_NAME.encode("ascii"),
        ),
    ),
)
def test_boundary_rejects_valid_binary_protected_content(
    tracked_repo: Path,
    filename: str,
    payload: bytes,
) -> None:
    (tracked_repo / filename).write_bytes(payload)
    _git(tracked_repo, "add", filename)
    assert _scan(tracked_repo) == 1


def test_boundary_rejects_javascript_hex_escape(tracked_repo: Path) -> None:
    escaped = "".join(f"\\x{value:02x}" for value in TEST_NAME.encode("ascii"))
    (tracked_repo / "mutant.js").write_text(
        f'const protectedName = "{escaped}";\n',
        encoding="utf-8",
    )
    _git(tracked_repo, "add", "mutant.js")
    assert _scan(tracked_repo) == 1


@pytest.mark.parametrize(
    "source",
    (
        "const protectedName = String.fromCharCode(113, 118, 120);\n",
        "const protectedName = String.fromCodePoint(113, 118, 120);\n",
        "const protectedName = String.fromCharCode(0x71, 0x76, 0x78);\n",
        "const protectedName = ['q', 'v', 'x'].join('');\n",
        'const protectedName = ["q", "v", "x"].join("");\n',
        "const protectedName = [`q`, `v`, `x`].join(``);\n",
        "const protectedName = 'qavbxa'.replaceAll('a', '').replaceAll('b', '');\n",
        "const protectedName = "
        "'qavbxa'.replace('a', '').replace('b', '').replace('a', '');\n",
    ),
)
def test_boundary_rejects_javascript_computed_forms(
    tracked_repo: Path,
    source: str,
) -> None:
    (tracked_repo / "mutant.js").write_text(source, encoding="utf-8")
    _git(tracked_repo, "add", "mutant.js")
    assert _scan(tracked_repo) == 1


@pytest.mark.parametrize(
    "source",
    (
        'PRIVATE = "qavbxa".replace("a", "").replace("b", "")\n',
        "PRIVATE = "
        + " + ".join(f"chr({value})" for value in TEST_NAME.encode("ascii"))
        + "\n",
        'PRIVATE = "".join(chr(value) for value in '
        + repr(tuple(TEST_NAME.encode("ascii")))
        + ")\n",
        'PRIVATE = "".join([chr(value) for value in '
        + repr(tuple(TEST_NAME.encode("ascii")))
        + "])\n",
        'PRIVATE = "".join([value for value in ' + repr(tuple(TEST_NAME)) + "])\n",
        'PRIVATE = "".join(map(chr, ' + repr(tuple(TEST_NAME.encode("ascii"))) + "))\n",
    ),
)
def test_boundary_rejects_python_replace_and_computed_forms(
    tracked_repo: Path,
    source: str,
) -> None:
    (tracked_repo / "mutant.py").write_text(source, encoding="utf-8")
    _git(tracked_repo, "add", "mutant.py")
    assert _scan(tracked_repo) == 1


@pytest.mark.parametrize(
    ("payload", "expected"),
    (
        (bytes((255, 0)) + b"QVM", 2),
        (bytes((255,)) + b"q\0v\0x", 1),
        (b"q" + bytes((255, 0)) + b"v" + bytes((255, 0)) + b"x", 2),
    ),
)
def test_boundary_fails_closed_for_invalid_utf8_with_nul_near_misses(
    tracked_repo: Path,
    payload: bytes,
    expected: int,
) -> None:
    (tracked_repo / "mutant.txt").write_bytes(payload)
    _git(tracked_repo, "add", "mutant.txt")
    assert _scan(tracked_repo) == expected


@pytest.mark.parametrize(
    ("encoded", "expected"),
    (
        (TEST_NAME.encode("ascii").hex(), 1),
        (b"nmr".hex(), 0),
    ),
)
def test_boundary_folds_bytes_fromhex_constants(
    tracked_repo: Path, encoded: str, expected: int
) -> None:
    source = f'PRIVATE = bytes.fromhex("{encoded}").decode("ascii")\n'
    (tracked_repo / "mutant.py").write_text(source, encoding="utf-8")
    _git(tracked_repo, "add", "mutant.py")
    assert _scan(tracked_repo) == expected


@pytest.mark.parametrize("broken", (False, True))
def test_boundary_scans_valid_and_broken_symlink_text(
    tracked_repo: Path, broken: bool
) -> None:
    target = f"{TEST_NAME}-backend-target"
    if not broken:
        (tracked_repo / target).write_text("public", encoding="utf-8")
    (tracked_repo / "public-link").symlink_to(target)
    _git(tracked_repo, "add", "public-link")
    assert _scan(tracked_repo) == 1


def test_boundary_scans_worktree_overlay_not_stale_index(tracked_repo: Path) -> None:
    path = tracked_repo / "proposed.txt"
    path.write_text(TEST_NAME, encoding="utf-8")
    _git(tracked_repo, "add", path.name)
    path.write_text("public", encoding="utf-8")
    assert _scan(tracked_repo) == 0

    path.write_text(TEST_NAME, encoding="utf-8")
    assert _scan(tracked_repo) == 1


def test_repository_scan_uses_the_production_digest() -> None:
    assert main(["--root", str(Path(__file__).resolve().parents[1])]) == 0
