"""Mutation evidence for the tracked-content public-boundary gate."""

from __future__ import annotations

from io import BytesIO
import hashlib
from pathlib import Path
import re
import struct
import subprocess
import tarfile
import zipfile
import zlib

import pytest
import scripts.check_public_boundary as boundary

from scripts.check_public_boundary import (
    ForbiddenIdentifier,
    _COMPOUND_IDENTIFIER,
    _HOST_IDENTIFIER,
    _PATH_IDENTIFIER,
    _URL_IDENTIFIER,
    _WORD_IDENTIFIER,
    main,
)


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


TEST_NAME = "qvx"
TEST_NAME_DIGEST = hashlib.sha256(TEST_NAME.encode("ascii")).hexdigest()


def _scan(
    root: Path,
    approved_binary_digests: dict[str, str] | None = None,
    forbidden_identifiers: tuple[ForbiddenIdentifier, ...] | None = None,
) -> int:
    private_digest = (
        hashlib.sha256(b"unused-token").hexdigest()
        if forbidden_identifiers is not None
        else TEST_NAME_DIGEST
    )
    kwargs = {"private_name_digest": private_digest}
    if approved_binary_digests is not None:
        kwargs["approved_binary_digests"] = approved_binary_digests
    if forbidden_identifiers is not None:
        kwargs["forbidden_identifiers"] = forbidden_identifiers
    return main(["--root", str(root)], **kwargs)


@pytest.mark.parametrize(
    ("category", "value", "pattern"),
    (
        ("name", "alpha", _WORD_IDENTIFIER),
        ("domain", "control.example.test", _HOST_IDENTIFIER),
        ("url", "https://control.example.test/private", _URL_IDENTIFIER),
        ("command", "private-cli", _COMPOUND_IDENTIFIER),
        ("path", "/srv/private/worktree", _PATH_IDENTIFIER),
        ("package", "private-package", _COMPOUND_IDENTIFIER),
        ("service", "private-service", _COMPOUND_IDENTIFIER),
        ("distribution", "restricted-release", _COMPOUND_IDENTIFIER),
        ("workspace", "private-workspace", _COMPOUND_IDENTIFIER),
        ("contract", "PrivateContract", _WORD_IDENTIFIER),
        ("host", "private-runner-42", _COMPOUND_IDENTIFIER),
    ),
)
def test_boundary_rejects_every_manifest_identifier_class(
    tracked_repo: Path, category: str, value: str, pattern: re.Pattern[str]
) -> None:
    identifier = ForbiddenIdentifier(
        category,
        hashlib.sha256(value.casefold().encode("utf-8")).hexdigest(),
        pattern,
    )
    (tracked_repo / "mutant.txt").write_text(value, encoding="utf-8")
    _git(tracked_repo, "add", "mutant.txt")
    assert _scan(tracked_repo, forbidden_identifiers=(identifier,)) == 1


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


@pytest.mark.parametrize("package_kind", ("wheel", "sdist"))
def test_boundary_inspects_built_package_members(
    tracked_repo: Path, package_kind: str
) -> None:
    artifact = tracked_repo / (
        "public-1.0-py3-none-any.whl"
        if package_kind == "wheel"
        else "public-1.0.tar.gz"
    )
    payload = BytesIO()
    if package_kind == "wheel":
        with zipfile.ZipFile(payload, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("public/module.py", TEST_NAME)
    else:
        content = TEST_NAME.encode("utf-8")
        with tarfile.open(fileobj=payload, mode="w:gz") as archive:
            member = tarfile.TarInfo("public/module.py")
            member.size = len(content)
            archive.addfile(member, BytesIO(content))
    artifact.write_bytes(payload.getvalue())
    assert (
        main(
            ["--root", str(tracked_repo), "--artifact", str(artifact)],
            private_name_digest=TEST_NAME_DIGEST,
            forbidden_identifiers=(),
            approved_binary_digests={},
        )
        == 1
    )


@pytest.mark.parametrize(
    "decoration",
    (
        "[https://control.example.test/private)",
        "private-package-v2.1.0",
        "private-package.backup",
        "private-package-1.0.whl",
    ),
)
def test_boundary_canonicalizes_decorated_identifiers(
    tracked_repo: Path, decoration: str
) -> None:
    is_url = decoration.startswith("[")
    value = "https://control.example.test/private" if is_url else "private-package"
    pattern = _URL_IDENTIFIER if is_url else _COMPOUND_IDENTIFIER
    identifier = ForbiddenIdentifier(
        "url" if is_url else "package",
        hashlib.sha256(value.encode()).hexdigest(),
        pattern,
    )
    (tracked_repo / "mutant.txt").write_text(decoration, encoding="utf-8")
    _git(tracked_repo, "add", "mutant.txt")
    assert _scan(tracked_repo, forbidden_identifiers=(identifier,)) == 1


@pytest.mark.parametrize("field", ("archive", "entry", "extra", "directory"))
def test_boundary_scans_zip_metadata_without_echoing_value(
    tracked_repo: Path, field: str, capsys: pytest.CaptureFixture[str]
) -> None:
    payload = BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        info = zipfile.ZipInfo(
            f"{TEST_NAME}/" if field == "directory" else "public.txt"
        )
        info.comment = TEST_NAME.encode() if field == "entry" else b""
        info.extra = (
            b"\x01\x00\x03\x00" + TEST_NAME.encode() if field == "extra" else b""
        )
        archive.writestr(info, b"public")
        archive.comment = TEST_NAME.encode() if field == "archive" else b""
    artifact = tracked_repo / "metadata.zip"
    artifact.write_bytes(payload.getvalue())
    result = main(
        ["--root", str(tracked_repo), "--artifact", str(artifact)],
        private_name_digest=TEST_NAME_DIGEST,
        forbidden_identifiers=(),
        approved_binary_digests={},
    )
    assert result == 1
    assert TEST_NAME not in capsys.readouterr().err


@pytest.mark.parametrize(
    "field", ("name", "linkname", "uname", "gname", "pax_key", "pax_value")
)
def test_boundary_scans_tar_metadata(tracked_repo: Path, field: str) -> None:
    payload = BytesIO()
    with tarfile.open(fileobj=payload, mode="w:gz") as archive:
        member = tarfile.TarInfo(TEST_NAME if field == "name" else "public-link")
        member.type = tarfile.SYMTYPE
        member.linkname = TEST_NAME if field == "linkname" else "public-target"
        member.uname = TEST_NAME if field == "uname" else "public"
        member.gname = TEST_NAME if field == "gname" else "public"
        if field == "pax_key":
            member.pax_headers[TEST_NAME] = "public"
        if field == "pax_value":
            member.pax_headers["public"] = TEST_NAME
        archive.addfile(member)
    artifact = tracked_repo / "metadata.tar.gz"
    artifact.write_bytes(payload.getvalue())
    assert (
        main(
            ["--root", str(tracked_repo), "--artifact", str(artifact)],
            private_name_digest=TEST_NAME_DIGEST,
            forbidden_identifiers=(),
            approved_binary_digests={},
        )
        == 1
    )


def test_boundary_rejects_unsupported_tar_special_member(tracked_repo: Path) -> None:
    payload = BytesIO()
    with tarfile.open(fileobj=payload, mode="w:gz") as archive:
        member = tarfile.TarInfo("public-device")
        member.type = tarfile.CHRTYPE
        archive.addfile(member)
    artifact = tracked_repo / "special.tar.gz"
    artifact.write_bytes(payload.getvalue())
    assert main(["--root", str(tracked_repo), "--artifact", str(artifact)]) == 2


def test_boundary_rejects_malformed_archive(tracked_repo: Path) -> None:
    artifact = tracked_repo / "malformed.zip"
    artifact.write_bytes(b"PK\x03\x04not-a-valid-archive")
    assert main(["--root", str(tracked_repo), "--artifact", str(artifact)]) == 2


def test_boundary_rejects_archive_member_limit(
    tracked_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(boundary, "_MAX_ARCHIVE_MEMBERS", 1)
    payload = BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr("one.txt", "public")
        archive.writestr("two.txt", "public")
    artifact = tracked_repo / "limited.zip"
    artifact.write_bytes(payload.getvalue())
    assert main(["--root", str(tracked_repo), "--artifact", str(artifact)]) == 2


def test_boundary_rejects_archive_expansion_limit(
    tracked_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(boundary, "_MAX_ARCHIVE_UNCOMPRESSED_BYTES", 3)
    payload = BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr("public.txt", "four")
    artifact = tracked_repo / "expanded.zip"
    artifact.write_bytes(payload.getvalue())
    assert main(["--root", str(tracked_repo), "--artifact", str(artifact)]) == 2


def test_boundary_rejects_nested_archive_limit(
    tracked_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(boundary, "_MAX_ARCHIVE_DEPTH", 1)
    nested = BytesIO()
    with zipfile.ZipFile(nested, "w") as archive:
        archive.writestr("public.txt", "public")
    outer = BytesIO()
    with zipfile.ZipFile(outer, "w") as archive:
        archive.writestr("nested.zip", nested.getvalue())
    artifact = tracked_repo / "nested.zip"
    artifact.write_bytes(outer.getvalue())
    assert main(["--root", str(tracked_repo), "--artifact", str(artifact)]) == 2


def test_nested_archives_share_one_cumulative_budget() -> None:
    payload = b"public-data"
    inner = BytesIO()
    with zipfile.ZipFile(inner, "w") as archive:
        archive.writestr("payload.txt", payload)
    inner_data = inner.getvalue()

    def outer(member_names: tuple[str, ...]) -> bytes:
        result = BytesIO()
        with zipfile.ZipFile(result, "w") as archive:
            for name in member_names:
                archive.writestr(name, inner_data)
        return result.getvalue()

    one_cost = len("one.zip") + len(inner_data) + len("payload.txt") + len(payload)
    one_budget = boundary.ArchiveBudget(one_cost, 10)
    assert (
        boundary._data_findings(
            Path("outer.zip"),
            outer(("one.zip",)),
            TEST_NAME_DIGEST,
            {},
            (),
            budget=one_budget,
        )
        == []
    )

    combined_budget = boundary.ArchiveBudget(one_cost, 10)
    with pytest.raises(ValueError, match="cumulative byte budget"):
        boundary._data_findings(
            Path("outer.zip"),
            outer(("one.zip", "two.zip")),
            TEST_NAME_DIGEST,
            {},
            (),
            budget=combined_budget,
        )


def test_boundary_rejects_compressed_input_before_full_read(
    tracked_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(boundary, "_MAX_ARCHIVE_COMPRESSED_BYTES", 3)
    artifact = tracked_repo / "oversized.zip"
    artifact.write_bytes(b"four")
    assert main(["--root", str(tracked_repo), "--artifact", str(artifact)]) == 2


def test_boundary_enforces_actual_member_read_limit() -> None:
    with pytest.raises(ValueError, match="member exceeds"):
        boundary._read_bounded(BytesIO(b"four"), 3)


def test_boundary_counts_tar_payload_and_pax_metadata(
    tracked_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = BytesIO()
    with tarfile.open(
        fileobj=payload, mode="w:gz", format=tarfile.PAX_FORMAT
    ) as archive:
        member = tarfile.TarInfo("public.txt")
        member.pax_headers["public-key"] = "public-value"
        member.size = 4
        archive.addfile(member, BytesIO(b"four"))
    monkeypatch.setattr(boundary, "_MAX_ARCHIVE_UNCOMPRESSED_BYTES", 3)
    artifact = tracked_repo / "budget.tar.gz"
    artifact.write_bytes(payload.getvalue())
    assert main(["--root", str(tracked_repo), "--artifact", str(artifact)]) == 2


def test_boundary_counts_zip_comment_and_extra_metadata(
    tracked_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        info = zipfile.ZipInfo("a")
        info.comment = b"comment"
        archive.writestr(info, b"")
        archive.comment = b"archive"
    monkeypatch.setattr(boundary, "_MAX_ARCHIVE_UNCOMPRESSED_BYTES", 3)
    artifact = tracked_repo / "budget.zip"
    artifact.write_bytes(payload.getvalue())
    assert main(["--root", str(tracked_repo), "--artifact", str(artifact)]) == 2


@pytest.mark.parametrize("kind", ("whl", "tar.gz"))
def test_boundary_scans_explicit_artifact_basename(
    tracked_repo: Path, kind: str, capsys: pytest.CaptureFixture[str]
) -> None:
    token = "private-package"
    identifier = ForbiddenIdentifier(
        "package", hashlib.sha256(token.encode()).hexdigest(), _COMPOUND_IDENTIFIER
    )
    artifact = tracked_repo / f"{token}-1.0.{kind}"
    payload = BytesIO()
    if kind == "whl":
        with zipfile.ZipFile(payload, "w") as archive:
            archive.writestr("public.txt", "public")
    else:
        with tarfile.open(fileobj=payload, mode="w:gz") as archive:
            member = tarfile.TarInfo("public.txt")
            member.size = 6
            archive.addfile(member, BytesIO(b"public"))
    artifact.write_bytes(payload.getvalue())
    result = main(
        ["--root", str(tracked_repo), "--artifact", str(artifact)],
        private_name_digest=hashlib.sha256(b"unused").hexdigest(),
        forbidden_identifiers=(identifier,),
        approved_binary_digests={},
    )
    assert result == 1
    assert token not in capsys.readouterr().err


def test_artifact_only_scan_ignores_transient_checkout_content(
    tracked_repo: Path,
) -> None:
    (tracked_repo / "transient.zip").write_bytes(b"PK\x03\x04invalid")
    artifact = tracked_repo / "public.whl"
    with zipfile.ZipFile(artifact, "w") as archive:
        archive.writestr("public.txt", "public")
    assert (
        main(
            [
                "--root",
                str(tracked_repo),
                "--artifacts-only",
                "--artifact",
                str(artifact),
            ],
            forbidden_identifiers=(),
            approved_binary_digests={},
        )
        == 0
    )


def test_artifact_only_scan_requires_explicit_artifact(
    tracked_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["--root", str(tracked_repo), "--artifacts-only"]) == 2
    assert "missing-artifact" in capsys.readouterr().err


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
