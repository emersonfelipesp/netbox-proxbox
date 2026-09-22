"""Fail closed when the proposed Git tree exposes private identifiers."""

from __future__ import annotations

import argparse
import ast
from collections.abc import Mapping
from dataclasses import dataclass
import gzip
import hashlib
from io import BytesIO
import os
from pathlib import Path
import re
import stat
import struct
import subprocess
import sys
import tarfile
import zipfile
import zlib


@dataclass(frozen=True)
class ForbiddenIdentifier:
    """One reviewed identifier class, stored without disclosing its value."""

    category: str
    digest: str
    pattern: re.Pattern[str]


@dataclass
class ArchiveBudget:
    """Mutable limits shared by one top-level archive and all nested members."""

    remaining_bytes: int
    remaining_members: int

    def charge_bytes(self, size: int) -> None:
        if size > self.remaining_bytes:
            raise ValueError("archive exceeds cumulative byte budget")
        self.remaining_bytes -= size

    def charge_member(self) -> None:
        if self.remaining_members < 1:
            raise ValueError("archive exceeds cumulative member budget")
        self.remaining_members -= 1


_WORD_IDENTIFIER = re.compile(r"[a-z0-9]+", re.IGNORECASE)
_HOST_IDENTIFIER = re.compile(r"[a-z0-9-]+(?:\.[a-z0-9-]+)+", re.IGNORECASE)
_URL_IDENTIFIER = re.compile(r"https?://[^\s\"'<>`]+", re.IGNORECASE)
_PATH_IDENTIFIER = re.compile(r"/(?:[a-z0-9._-]+/)*[a-z0-9._-]+", re.IGNORECASE)
_COMPOUND_IDENTIFIER = re.compile(r"[a-z0-9]+(?:[-_.][a-z0-9]+)+", re.IGNORECASE)
_FORBIDDEN_IDENTIFIERS = (
    ForbiddenIdentifier(
        "name",
        "00e1e10b7f275ff455afed38eb08cb1bfcc007805f50e0d6e8573f503a63f4be",
        _WORD_IDENTIFIER,
    ),
    ForbiddenIdentifier(
        "domain",
        "576ddfa7bccc00515b8ac49966d5d5422bbacc3035604c89f4bd1b1156c59cad",
        _HOST_IDENTIFIER,
    ),
    ForbiddenIdentifier(
        "url",
        "7bcd2e5385d81a914078e04c622a8780eb7b59ea2411f1ce78ba6deb18f6dd17",
        _URL_IDENTIFIER,
    ),
    ForbiddenIdentifier(
        "command",
        "00e1e10b7f275ff455afed38eb08cb1bfcc007805f50e0d6e8573f503a63f4be",
        _WORD_IDENTIFIER,
    ),
    ForbiddenIdentifier(
        "path",
        "26bc7a79cd68f57928f3f7db21d1145753b014383e20d8185f2fb5a157fc364b",
        _PATH_IDENTIFIER,
    ),
    ForbiddenIdentifier(
        "package",
        "5c719a925ed5521afb861a83300c7782103f22a2d49a223d93a66914c18b4645",
        _COMPOUND_IDENTIFIER,
    ),
    ForbiddenIdentifier(
        "service",
        "0624331dd76c08e10732893dc6a22155b60e23a2d3937984157d23f77f500699",
        _COMPOUND_IDENTIFIER,
    ),
    ForbiddenIdentifier(
        "distribution",
        "ea624d243626d7f3bbdeaf7c58711b824702963fd2e71bf74fe451872d947c20",
        _COMPOUND_IDENTIFIER,
    ),
    ForbiddenIdentifier(
        "workspace",
        "ca7573d4012c1230fc5da3de3bd61ffc28bcdc18d8742404d32de7174bc51121",
        _COMPOUND_IDENTIFIER,
    ),
    ForbiddenIdentifier(
        "contract",
        "9851abb282006b6aa941f4689303c5a5dc0920ff197d59c9ac62b68261a494b0",
        _WORD_IDENTIFIER,
    ),
    ForbiddenIdentifier(
        "host",
        "bab7bd5fce43127fde0a8768adc63ea541e4621a7bf8c2924bd307e5ca4936d4",
        _COMPOUND_IDENTIFIER,
    ),
)
_PRIVATE_NAME_DIGEST = _FORBIDDEN_IDENTIFIERS[0].digest
_WORD_PATTERN = re.compile(r"[a-z0-9]+", re.IGNORECASE)
_BINARY_SUFFIXES = {
    ".eot",
    ".gif",
    ".gz",
    ".ico",
    ".jpeg",
    ".jpg",
    ".png",
    ".pyc",
    ".ttf",
    ".webp",
    ".woff",
    ".woff2",
    ".whl",
    ".zip",
}
_MAX_ARCHIVE_MEMBERS = 10_000
_MAX_ARCHIVE_COMPRESSED_BYTES = 100 * 1024 * 1024
_MAX_ARCHIVE_UNCOMPRESSED_BYTES = 100 * 1024 * 1024
_MAX_ARCHIVE_DEPTH = 3
_APPROVED_BINARY_DIGESTS = {
    "docs/.icons/favicon.ico": "b82a2f30b29620a932a43426a7e88d6bac551567c578d00b0c50664c0331d3cc",
    "docs/assets/screenshots/backup-detail.png": "da4c444b201e8f92df4c8245d57754d33ef2da74db414f32b7a3432dbfd1ed83",
    "docs/assets/screenshots/backup-routine-detail.png": "ed30560c63b4bec989a7467c18cef126282b3a82fb3c4d38ef8fdd2546b04623",
    "docs/assets/screenshots/backup-routines.png": "74c34b4f3ac87e6c615b67dca56040fec7995406ac76b0aaec285b9f71143a7d",
    "docs/assets/screenshots/backups.png": "e316233ffe858978602de2f8a9ae1c51e45d2cde66317a0a63f823f56f2641b0",
    "docs/assets/screenshots/clusters.png": "9b96e7fd2e8f3e8a27e287e9ca60197adc2956104bda57d68e0850e3ab413a45",
    "docs/assets/screenshots/dashboard.png": "23683f5b931fcdd46c6ab0c49592c0ef81f853ed810effe56ec202818b500244",
    "docs/assets/screenshots/fastapi-endpoint-detail.png": "545448d0cb1f7b2892adf9be4bc57ae2633e2ac679af595621e7910aad34680d",
    "docs/assets/screenshots/fastapi-endpoints.png": "b7fe57a2956ffff8c1d3455c2baffc1c785f17acfc532f89e08597f96c739e4a",
    "docs/assets/screenshots/home.png": "991c6122c14050f63577d6067c4ca1a98a54290962d4f868304e7ce0ba56fc0b",
    "docs/assets/screenshots/lxc-container-detail.png": "6f1a77c77b79ef9fc9224676a760ecec37e9156bdc5dc1ae85282faf945c699d",
    "docs/assets/screenshots/lxc-containers.png": "74f2a2fff8e7196df865d90bccb44cbc4c526107676644b131043afc7a7a85c0",
    "docs/assets/screenshots/netbox-endpoint-detail.png": "a677743a57d6537c8f216a980fab4c07d0a3b8dff69dcdfd99ba4fb6921356aa",
    "docs/assets/screenshots/netbox-endpoints.png": "65f5dd04c6c68a081903fb889631cdc5fec1f0f83a9fbe4df81e6ea94ccbf2b4",
    "docs/assets/screenshots/nodes.png": "cce1fc26e094bf913fa7cd1abd90fd243ae26b9e29230bb8907cd42627522f78",
    "docs/assets/screenshots/proxmox-endpoint-detail.png": "ae478521430ea40c6a1126150b73ed35a0e1ff7ec339459d0ba80fb20dc04497",
    "docs/assets/screenshots/proxmox-endpoint-settings.png": "4a27db624327a2be59b62640576e62be0baa09f1e7a9423e7247cf3558c588fb",
    "docs/assets/screenshots/proxmox-endpoints.png": "726014e4ac879e6ec289a412ea568208caf9cebb323f5eab08ce20b05ab9f7a9",
    "docs/assets/screenshots/replications.png": "100795b2710f3a1375fe1da2c559fc0837349af0c2a5e455524c52790c462074",
    "docs/assets/screenshots/snapshot-detail.png": "cc26de52c716b9ccd76d140103e7f4a2ae26ec4ed78abf8e0fa8f1a42c05277f",
    "docs/assets/screenshots/snapshots.png": "a6e9d2bd12d7eb07b53f2ade8386a201b5e972945f75c8b06544acf4d4fc9114",
    "docs/assets/screenshots/storage-detail.png": "67dc4968e77997bb39f4e3f4bd51a1341d788f0aebb54096eb5759e49125b9ac",
    "docs/assets/screenshots/storage.png": "3b54cc8f6d877af507d06c270fbcef34f2e32999564233967c51803b77724841",
    "docs/assets/screenshots/task-history-detail.png": "a65977191bc1488c9ca7eb6c9449887431f1e526b235a2e25c84c8353826337c",
    "docs/assets/screenshots/task-history.png": "a4e79093c6cacb5cfd4142e218b8f6ef3f45b67a1808262397bc8b0a45d870c0",
    "docs/assets/screenshots/virtual-machine-detail.png": "fcdb0012aa1e3e1cb00b66f1f78d31281e1f248f3549653bc3c7c983c6b2886d",
    "docs/assets/screenshots/virtual-machines.png": "4e05c8da28a595521ff08834b1672b01c369e99c87af3ef46675421203b70280",
    "docs/backend/proxbox-architecture.png": "24a46d12c2e4132f333c8137ac0dd0c497c61b0e552d309f6525bd3114196749",
    "docs/etc/img/custom_field_example.png": "6e572d25a4b338e8ff4acbfcf8cc18b24302d448442555bbfc71d639d984013a",
    "docs/etc/img/proxbox-full-logo.png": "171d43be29a05dd9b80b8343ebb6ad9df4a1868784f67182f66eb1c88bedadb6",
    "docs/etc/img/proxbox.png": "1ff170437cc07d4ad4c7ae585128bbd0688462609889e8fc1a4dc42791331edc",
    "docs/etc/img/proxbox_full_update_button.png": "fa3374f95d57f5fc70e5f2ab858f28d9d0a3ab112bd50c8fec520fe31925e172",
    "etc/img/custom_field_example.png": "6e572d25a4b338e8ff4acbfcf8cc18b24302d448442555bbfc71d639d984013a",
    "etc/img/proxbox-full-logo.png": "171d43be29a05dd9b80b8343ebb6ad9df4a1868784f67182f66eb1c88bedadb6",
    "etc/img/proxbox-services.png": "aab24d7136d45e0cdd77b592e32857173fc49f3d30b258f31b913adda0b4d553",
    "etc/img/proxbox.png": "1ff170437cc07d4ad4c7ae585128bbd0688462609889e8fc1a4dc42791331edc",
    "etc/img/proxbox_full_update_button.png": "fa3374f95d57f5fc70e5f2ab858f28d9d0a3ab112bd50c8fec520fe31925e172",
    "netbox_proxbox/static/netbox_proxbox/fastapi_logo.png": "ca78f425533c5bdaad6bc5e80be0956b5bb952b4aba9d3f1461f1adcf08f6f76",
    "netbox_proxbox/static/netbox_proxbox/github.png": "d83ddf4ea98e9d2e77848869cbe5f0ecabb3058ede22c681bbe07b45a9091909",
    "netbox_proxbox/static/netbox_proxbox/linkedin.png": "e530ef19b89d0e62ad2b5c712e4b62be44a26ad4364f9b700adc0db64b7d894e",
    "netbox_proxbox/static/netbox_proxbox/styles/materialdesignicons-webfont-DWVXV5L5.woff": "48d3eec6ab70dc7a1908f9ba2f208e0a58718b9ee16e3f6abdb5db4f461fa258",
    "netbox_proxbox/static/netbox_proxbox/styles/materialdesignicons-webfont-ER2MFQKM.woff2": "e52d60f64267cdaa08422b50bab5d45bd35e662b03b9af75179ceae00ac5fc8b",
    "netbox_proxbox/static/netbox_proxbox/styles/materialdesignicons-webfont-UHEFFMSX.eot": "861aea0548ccc9af98dec520be340b8e2d4beb97ba34893ac9af511a449e3fa2",
    "netbox_proxbox/static/netbox_proxbox/styles/materialdesignicons-webfont-WM6M6ZHQ.ttf": "bd725a7a38939e5b59904e1b7a7265919ecec256166ece69d515c21005165907",
}
_FRAGMENT_PATTERNS = (
    re.compile(
        r"""[\"'](?P<a>[a-z0-9])[\"']\s*\+\s*[\"'](?P<b>[a-z0-9])[\"']\s*\+\s*[\"'](?P<c>[a-z0-9])[\"']""",
        re.IGNORECASE,
    ),
    re.compile(
        r"""join\s*\(\s*[\(\[]\s*[\"'](?P<a>[a-z0-9])[\"']\s*,\s*[\"'](?P<b>[a-z0-9])[\"']\s*,\s*[\"'](?P<c>[a-z0-9])[\"']""",
        re.IGNORECASE,
    ),
)
_ESCAPED_TEXT_PATTERNS = (
    re.compile(r"(?:\\x[0-9a-f]{2}){3,}", re.IGNORECASE),
    re.compile(r"(?:\\u[0-9a-f]{4}){3,}", re.IGNORECASE),
)
_JAVASCRIPT_CODEPOINT_PATTERN = re.compile(
    r"String\.from(?:CharCode|CodePoint)\(\s*"
    r"(?P<values>(?:0[xX][0-9a-fA-F]+|[0-9]+)"
    r"(?:\s*,\s*(?:0[xX][0-9a-fA-F]+|[0-9]+))*)\s*\)",
)
_JAVASCRIPT_ARRAY_JOIN_PATTERN = re.compile(
    r"\[(?P<values>(?:\s*[\"'`][a-z0-9][\"'`]\s*,?)+)\]"
    r"\.join\(\s*(?:[\"'`][\"'`])\s*\)",
    re.IGNORECASE,
)
_JAVASCRIPT_QUOTED_CHARACTER_PATTERN = re.compile(
    r"[\"'`](?P<value>[a-z0-9])[\"'`]",
    re.IGNORECASE,
)
_JAVASCRIPT_REPLACE_PATTERN = re.compile(
    r"(?P<expression>[\"'`][a-z0-9]+[\"'`]"
    r"(?:\.replace(?:All)?\(\s*[\"'`][a-z0-9]*[\"'`]\s*,"
    r"\s*[\"'`][a-z0-9]*[\"'`]\s*\)){1,32})",
    re.IGNORECASE,
)
_JAVASCRIPT_REPLACE_CALL_PATTERN = re.compile(
    r"\.replace(?P<all>All)?\(\s*[\"'`](?P<old>[a-z0-9]*)[\"'`]\s*,"
    r"\s*[\"'`](?P<new>[a-z0-9]*)[\"'`]\s*\)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ProposedFile:
    """One file-like entry in the worktree-over-index proposed tree."""

    relative_path: Path
    git_mode: str
    data: bytes


def _contains_private_name(
    value: str,
    private_name_digest: str = _PRIVATE_NAME_DIGEST,
) -> bool:
    """Compare identifier words by digest so the scanner does not disclose one."""
    for word in _WORD_PATTERN.findall(value.casefold()):
        if hashlib.sha256(word.encode("utf-8")).hexdigest() == private_name_digest:
            return True
    return False


def _identifier_categories(
    value: str,
    identifiers: tuple[ForbiddenIdentifier, ...] = _FORBIDDEN_IDENTIFIERS,
) -> set[str]:
    """Return forbidden classes whose reviewed digest matches literal text."""
    categories: set[str] = set()
    for identifier in identifiers:
        for match in identifier.pattern.finditer(value):
            candidates = _identifier_candidates(identifier.category, match.group(0))
            if any(_digest(candidate) == identifier.digest for candidate in candidates):
                categories.add(identifier.category)
    return categories


def _digest(value: str) -> str:
    return hashlib.sha256(value.casefold().encode("utf-8")).hexdigest()


def _identifier_candidates(category: str, value: str) -> tuple[str, ...]:
    """Include normalized prefixes so decorated identifiers cannot hide."""
    value = value.rstrip(").,;:]}>'\"")
    if category in {"url", "path"}:
        parts = value.split("/")
        return tuple("/".join(parts[:end]) for end in range(2, len(parts) + 1))
    if category in {"package", "service", "distribution", "workspace"}:
        parts = re.split(r"[-_.]", value)
        separators = [match.group(0) for match in re.finditer(r"[-_.]", value)]
        prefixes = [parts[0]]
        for separator, part in zip(separators, parts[1:], strict=False):
            prefixes.append(prefixes[-1] + separator + part)
        return tuple(prefixes)
    return (value,)


def _run_git(root: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
    )
    return result.stdout


def _index_entries(root: Path) -> dict[Path, tuple[str, str]]:
    """Read stage-zero paths, modes, and blob IDs from Git's index."""
    entries: dict[Path, tuple[str, str]] = {}
    for record in _run_git(root, "ls-files", "-s", "-z", "--cached").split(b"\0"):
        if not record:
            continue
        metadata, raw_path = record.split(b"\t", 1)
        mode, object_id, stage = metadata.decode("ascii").split()
        if stage == "0":
            entries[Path(os.fsdecode(raw_path))] = (mode, object_id)
    return entries


def _git_blobs(root: Path, object_ids: set[str]) -> dict[str, bytes]:
    """Load indexed blobs in one checked Git batch operation."""
    if not object_ids:
        return {}
    ordered_ids = sorted(object_ids)
    result = subprocess.run(
        ["git", "-C", str(root), "cat-file", "--batch"],
        input=("\n".join(ordered_ids) + "\n").encode("ascii"),
        check=True,
        capture_output=True,
    )
    blobs: dict[str, bytes] = {}
    offset = 0
    for expected_id in ordered_ids:
        header_end = result.stdout.find(b"\n", offset)
        if header_end < 0:
            raise ValueError("Git blob batch ended before its header")
        object_id, object_type, raw_size = result.stdout[offset:header_end].split()
        size = int(raw_size)
        data_start = header_end + 1
        data_end = data_start + size
        if (
            object_id.decode("ascii") != expected_id
            or object_type != b"blob"
            or data_end >= len(result.stdout)
            or result.stdout[data_end : data_end + 1] != b"\n"
        ):
            raise ValueError(f"Git returned an invalid blob batch for {expected_id}")
        blobs[expected_id] = result.stdout[data_start:data_end]
        offset = data_end + 1
    if offset != len(result.stdout):
        raise ValueError("Git blob batch contained unexpected trailing data")
    return blobs


def _worktree_entry(
    root: Path, relative_path: Path, index_mode: str
) -> ProposedFile | None:
    """Read a regular file or symlink without following its target."""
    path = root / relative_path
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return None
    if stat.S_ISLNK(metadata.st_mode):
        return ProposedFile(relative_path, "120000", os.fsencode(os.readlink(path)))
    if stat.S_ISREG(metadata.st_mode):
        mode = "100755" if metadata.st_mode & stat.S_IXUSR else "100644"
        return ProposedFile(relative_path, mode, path.read_bytes())
    if index_mode == "160000" and stat.S_ISDIR(metadata.st_mode):
        return None
    raise OSError(f"unsupported worktree entry type: {relative_path}")


def proposed_files(root: Path) -> tuple[ProposedFile, ...]:
    """Overlay worktree changes and untracked files on Git's stage-zero index."""
    index_entries = _index_entries(root)
    changed = {
        Path(os.fsdecode(entry))
        for entry in _run_git(
            root,
            "ls-files",
            "-z",
            "--modified",
            "--deleted",
        ).split(b"\0")
        if entry
    }
    untracked = {
        Path(os.fsdecode(entry))
        for entry in _run_git(
            root,
            "ls-files",
            "-z",
            "--others",
            "--exclude-standard",
        ).split(b"\0")
        if entry
    }
    blob_ids = {
        object_id
        for relative_path, (mode, object_id) in index_entries.items()
        if relative_path not in changed and mode != "160000"
    }
    indexed_blobs = _git_blobs(root, blob_ids)
    files: list[ProposedFile] = []
    for relative_path in sorted(set(index_entries) | untracked, key=os.fspath):
        indexed = index_entries.get(relative_path)
        if indexed is not None and relative_path not in changed:
            mode, object_id = indexed
            if mode != "160000":
                files.append(
                    ProposedFile(relative_path, mode, indexed_blobs[object_id])
                )
            continue
        index_mode = indexed[0] if indexed is not None else ""
        entry = _worktree_entry(root, relative_path, index_mode)
        if entry is not None:
            files.append(entry)
    return tuple(files)


def _constant_chr_call(arguments: list[ast.expr]) -> str | None:
    if len(arguments) != 1:
        return None
    value = _constant_value(arguments[0])
    return chr(value) if isinstance(value, int) and 0 <= value <= 0x10FFFF else None


def _constant_map_call(arguments: list[ast.expr]) -> list[str] | None:
    if len(arguments) != 2:
        return None
    function, source = arguments
    if not isinstance(function, ast.Name) or function.id != "chr":
        return None
    values = _constant_value(source)
    if not isinstance(values, list):
        return None
    if not all(isinstance(value, int) and 0 <= value <= 0x10FFFF for value in values):
        return None
    return [chr(value) for value in values]


def _constant_bytes_call(arguments: list[ast.expr]) -> bytes | None:
    if len(arguments) != 1:
        return None
    values = _constant_value(arguments[0])
    if not isinstance(values, list):
        return None
    if not all(isinstance(value, int) and 0 <= value <= 255 for value in values):
        return None
    return bytes(values)


def _constant_named_call_value(node: ast.Call) -> object | None:
    """Fold allowlisted calls whose callable is a bare built-in name."""
    if not isinstance(node.func, ast.Name):
        return None
    handlers = {
        "bytes": _constant_bytes_call,
        "chr": _constant_chr_call,
        "map": _constant_map_call,
    }
    handler = handlers.get(node.func.id)
    return handler(node.args) if handler is not None else None


def _constant_fromhex_call(node: ast.Call) -> bytes | None:
    if len(node.args) != 1:
        return None
    encoded = _constant_value(node.args[0])
    if not isinstance(encoded, str):
        return None
    try:
        return bytes.fromhex(encoded)
    except ValueError:
        return None


def _constant_replace_call(
    owner: str | bytes,
    arguments: list[ast.expr],
) -> str | bytes | None:
    values = [_constant_value(argument) for argument in arguments]
    if len(values) not in {2, 3}:
        return None
    if not all(isinstance(value, type(owner)) for value in values[:2]):
        return None
    if len(values) == 3 and not isinstance(values[2], int):
        return None
    return owner.replace(*values)


def _constant_decode_call(owner: object, arguments: list[ast.expr]) -> str | None:
    if not isinstance(owner, bytes) or len(arguments) > 1:
        return None
    encoding = _constant_value(arguments[0]) if arguments else "utf-8"
    return owner.decode(encoding) if encoding in {"ascii", "utf-8"} else None


def _constant_join_call(owner: object, arguments: list[ast.expr]) -> object | None:
    if not isinstance(owner, (str, bytes)) or len(arguments) != 1:
        return None
    values = _constant_value(arguments[0])
    if not isinstance(values, list):
        return None
    if not all(isinstance(value, type(owner)) for value in values):
        return None
    return owner.join(values)


def _constant_attribute_call_value(node: ast.Call) -> object | None:
    """Fold allowlisted calls whose callable is a constant's attribute."""
    if not isinstance(node.func, ast.Attribute):
        return None
    if (
        node.func.attr == "fromhex"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "bytes"
    ):
        return _constant_fromhex_call(node)
    owner = _constant_value(node.func.value)
    if node.func.attr == "replace" and isinstance(owner, (str, bytes)):
        return _constant_replace_call(owner, node.args)
    if node.func.attr == "decode":
        return _constant_decode_call(owner, node.args)
    if node.func.attr == "join":
        return _constant_join_call(owner, node.args)
    return None


def _constant_call_value(node: ast.Call) -> object | None:
    """Fold the allowlisted inert call forms used in constant construction."""
    if isinstance(node.func, ast.Name):
        return _constant_named_call_value(node)
    return _constant_attribute_call_value(node)


def _constant_generator_source(
    node: ast.GeneratorExp | ast.ListComp,
) -> tuple[str, list[object]] | None:
    if len(node.generators) != 1:
        return None
    generator = node.generators[0]
    if (
        generator.is_async
        or generator.ifs
        or not isinstance(generator.target, ast.Name)
    ):
        return None
    source = _constant_value(generator.iter)
    return (generator.target.id, source) if isinstance(source, list) else None


def _constant_generator_values(
    node: ast.GeneratorExp | ast.ListComp,
) -> list[object] | None:
    """Fold a single inert generator over literal values."""
    resolved = _constant_generator_source(node)
    if resolved is None:
        return None
    target_name, source = resolved
    if isinstance(node.elt, ast.Name) and node.elt.id == target_name:
        return source
    if not (
        isinstance(node.elt, ast.Call)
        and isinstance(node.elt.func, ast.Name)
        and node.elt.func.id == "chr"
        and len(node.elt.args) == 1
        and isinstance(node.elt.args[0], ast.Name)
        and node.elt.args[0].id == target_name
        and all(isinstance(value, int) and 0 <= value <= 0x10FFFF for value in source)
    ):
        return None
    return [chr(value) for value in source]


def _constant_sequence_value(node: ast.Tuple | ast.List) -> list[object] | None:
    values = [_constant_value(item) for item in node.elts]
    return values if all(value is not None for value in values) else None


def _constant_add_value(node: ast.BinOp) -> str | bytes | None:
    if not isinstance(node.op, ast.Add):
        return None
    left = _constant_value(node.left)
    right = _constant_value(node.right)
    if isinstance(left, str) and isinstance(right, str):
        return left + right
    if isinstance(left, bytes) and isinstance(right, bytes):
        return left + right
    return None


def _constant_joined_string(node: ast.JoinedStr) -> str | None:
    parts = [_constant_value(item) for item in node.values]
    return "".join(parts) if all(isinstance(part, str) for part in parts) else None


def _constant_value(node: ast.AST) -> object | None:
    """Fold only inert literal operations used to fragment protected names."""
    if isinstance(node, ast.Constant):
        return node.value if isinstance(node.value, (str, bytes, int)) else None
    if isinstance(node, (ast.Tuple, ast.List)):
        return _constant_sequence_value(node)
    if isinstance(node, ast.BinOp):
        return _constant_add_value(node)
    if isinstance(node, ast.JoinedStr):
        return _constant_joined_string(node)
    if isinstance(node, (ast.GeneratorExp, ast.ListComp)):
        return _constant_generator_values(node)
    return _constant_call_value(node) if isinstance(node, ast.Call) else None


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _fragment_findings(text: str, private_name_digest: str) -> set[int]:
    """Return lines containing allowlisted literal-fragment constructions."""
    findings: set[int] = set()
    for pattern in _FRAGMENT_PATTERNS:
        for match in pattern.finditer(text):
            value = "".join(match.group(name) for name in ("a", "b", "c"))
            if _contains_private_name(value, private_name_digest):
                findings.add(_line_number(text, match.start()))
    return findings


def _escaped_text_findings(text: str, private_name_digest: str) -> set[int]:
    """Return lines containing hex-escaped protected names in authored text."""
    findings: set[int] = set()
    for pattern in _ESCAPED_TEXT_PATTERNS:
        width = 2 if "x" in pattern.pattern else 4
        for match in pattern.finditer(text):
            encoded = match.group(0)
            value = "".join(
                chr(int(encoded[offset + 2 : offset + 2 + width], 16))
                for offset in range(0, len(encoded), width + 2)
            )
            if _contains_private_name(value, private_name_digest):
                findings.add(_line_number(text, match.start()))
    return findings


def _javascript_codepoint_findings(
    text: str,
    private_name_digest: str,
) -> set[int]:
    findings: set[int] = set()
    for match in _JAVASCRIPT_CODEPOINT_PATTERN.finditer(text):
        raw_values = [value.strip() for value in match.group("values").split(",")]
        try:
            values = [int(value, 0) for value in raw_values]
        except ValueError:
            findings.add(_line_number(text, match.start()))
            continue
        if not values or len(values) > 256 or any(value > 0x10FFFF for value in values):
            findings.add(_line_number(text, match.start()))
            continue
        reconstructed = "".join(chr(value) for value in values)
        if _contains_private_name(reconstructed, private_name_digest):
            findings.add(_line_number(text, match.start()))
    return findings


def _javascript_array_join_findings(
    text: str,
    private_name_digest: str,
) -> set[int]:
    findings: set[int] = set()
    for match in _JAVASCRIPT_ARRAY_JOIN_PATTERN.finditer(text):
        values = _JAVASCRIPT_QUOTED_CHARACTER_PATTERN.findall(match.group("values"))
        if len(values) > 256 or _contains_private_name(
            "".join(values), private_name_digest
        ):
            findings.add(_line_number(text, match.start()))
    return findings


def _javascript_replace_findings(
    text: str,
    private_name_digest: str,
) -> set[int]:
    findings: set[int] = set()
    for match in _JAVASCRIPT_REPLACE_PATTERN.finditer(text):
        expression = match.group("expression")
        value = expression[1 : expression.find(expression[0], 1)]
        for call in _JAVASCRIPT_REPLACE_CALL_PATTERN.finditer(expression):
            old = call.group("old")
            new = call.group("new")
            value = (
                value.replace(old, new)
                if call.group("all")
                else value.replace(old, new, 1)
            )
        if _contains_private_name(value, private_name_digest):
            findings.add(_line_number(text, match.start()))
    return findings


def _javascript_findings(text: str, private_name_digest: str) -> set[int]:
    findings = _javascript_codepoint_findings(text, private_name_digest)
    findings.update(_javascript_array_join_findings(text, private_name_digest))
    findings.update(_javascript_replace_findings(text, private_name_digest))
    return findings


def _manifest_text_findings(
    text: str, identifiers: tuple[ForbiddenIdentifier, ...]
) -> set[int]:
    findings: set[int] = set()
    for identifier in identifiers:
        for match in identifier.pattern.finditer(text):
            candidates = _identifier_candidates(identifier.category, match.group(0))
            if any(_digest(candidate) == identifier.digest for candidate in candidates):
                findings.add(_line_number(text, match.start()))
    return findings


def _python_constant_findings(text: str, private_name_digest: str) -> set[int]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return set()
    findings: set[int] = set()
    for node in ast.walk(tree):
        value = _constant_value(node)
        if isinstance(value, bytes):
            value = value.decode("utf-8", errors="ignore")
        if isinstance(value, str) and _contains_private_name(
            value, private_name_digest
        ):
            findings.add(getattr(node, "lineno", 1))
    return findings


def _private_word_findings(text: str, private_name_digest: str) -> set[int]:
    return {
        _line_number(text, match.start())
        for match in _WORD_PATTERN.finditer(text)
        if _contains_private_name(match.group(0), private_name_digest)
    }


def _text_findings(
    relative_path: Path,
    text: str,
    private_name_digest: str = _PRIVATE_NAME_DIGEST,
    forbidden_identifiers: tuple[ForbiddenIdentifier, ...] = _FORBIDDEN_IDENTIFIERS,
) -> list[str]:
    findings = _manifest_text_findings(text, forbidden_identifiers)
    findings.update(_private_word_findings(text, private_name_digest))
    findings.update(_fragment_findings(text, private_name_digest))
    findings.update(_escaped_text_findings(text, private_name_digest))
    if relative_path.suffix in {".js", ".jsx", ".mjs", ".cjs"}:
        findings.update(_javascript_findings(text, private_name_digest))
    if relative_path.suffix == ".py":
        findings.update(_python_constant_findings(text, private_name_digest))
    return [f"tracked content line {line_number}" for line_number in sorted(findings)]


def _valid_png(data: bytes) -> bool:
    """Validate the complete PNG chunk envelope, including every CRC."""
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return False
    offset = 8
    chunk_number = 0
    while offset + 12 <= len(data):
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        kind = data[offset + 4 : offset + 8]
        payload_end = offset + 8 + length
        chunk_end = payload_end + 4
        if chunk_end > len(data):
            return False
        expected_crc = struct.unpack(">I", data[payload_end:chunk_end])[0]
        if zlib.crc32(kind + data[offset + 8 : payload_end]) != expected_crc:
            return False
        if chunk_number == 0 and (kind != b"IHDR" or length != 13):
            return False
        if kind == b"IEND":
            return length == 0 and chunk_end == len(data)
        chunk_number += 1
        offset = chunk_end
    return False


def _valid_icon(data: bytes) -> bool:
    """Validate the ICO header, directory, and every declared payload range."""
    if len(data) < 6 or data[:4] != b"\x00\x00\x01\x00":
        return False
    count = struct.unpack("<H", data[4:6])[0]
    directory_end = 6 + (count * 16)
    if count == 0 or directory_end > len(data):
        return False
    for offset in range(6, directory_end, 16):
        size, image_offset = struct.unpack("<II", data[offset + 8 : offset + 16])
        if size == 0 or image_offset < directory_end or image_offset + size > len(data):
            return False
    return True


def _valid_sized_container(data: bytes, signature: bytes) -> bool:
    """Validate RIFF/WOFF family signatures and their declared total length."""
    if len(data) < 12 or not data.startswith(signature):
        return False
    if signature == b"RIFF":
        return data[8:12] == b"WEBP" and struct.unpack("<I", data[4:8])[0] + 8 == len(
            data
        )
    return struct.unpack(">I", data[8:12])[0] == len(data)


def _valid_eot(data: bytes) -> bool:
    """Validate the fixed EOT header sizes and magic number."""
    if len(data) < 36:
        return False
    total_size, font_size = struct.unpack("<II", data[:8])
    return (
        total_size == len(data) and font_size <= len(data) - 36 and data[34:36] == b"LP"
    )


def _valid_sfnt(data: bytes) -> bool:
    """Validate a TrueType/OpenType table directory and every payload range."""
    if len(data) < 12 or data[:4] not in {b"\x00\x01\x00\x00", b"OTTO"}:
        return False
    table_count = struct.unpack(">H", data[4:6])[0]
    directory_end = 12 + (table_count * 16)
    if table_count == 0 or directory_end > len(data):
        return False
    for offset in range(12, directory_end, 16):
        table_offset, table_length = struct.unpack(
            ">II", data[offset + 8 : offset + 16]
        )
        if table_offset < directory_end or table_offset + table_length > len(data):
            return False
    return True


def _structured_binary_kind(data: bytes) -> str | None:
    """Return the validated kind for structured image and font containers."""
    if data[:4] in {b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"}:
        return "zip"
    if _valid_png(data):
        return "opaque"
    if _valid_icon(data):
        return "opaque"
    if _valid_sized_container(data, b"RIFF"):
        return "opaque"
    if _valid_sized_container(data, b"wOFF"):
        return "opaque"
    if _valid_sized_container(data, b"wOF2"):
        return "opaque"
    if _valid_eot(data) or _valid_sfnt(data):
        return "opaque"
    return None


def _simple_image_kind(data: bytes) -> str | None:
    """Recognize bounded image envelopes without adding scanner branches."""
    if data.startswith(b"\xff\xd8\xff") and data.endswith(b"\xff\xd9"):
        return "opaque"
    if data[:6] in {b"GIF87a", b"GIF89a"} and data.endswith(b";"):
        return "opaque"
    return None


def _recognized_binary_kind(relative_path: Path, data: bytes) -> str | None:
    """Return a structurally validated kind; suffix or magic alone is insufficient."""
    if relative_path.suffix.casefold() not in _BINARY_SUFFIXES:
        return None
    if relative_path.name.casefold().endswith(".tar.gz") and data.startswith(
        b"\x1f\x8b"
    ):
        return "tar"
    return _structured_binary_kind(data) or _simple_image_kind(data)


def _tar_findings(
    relative_path: Path,
    data: bytes,
    private_name_digest: str,
    approved_binary_digests: Mapping[str, str],
    forbidden_identifiers: tuple[ForbiddenIdentifier, ...],
    depth: int,
    budget: ArchiveBudget,
) -> list[str]:
    """Inspect every bounded regular member in a gzip-compressed source archive."""
    if depth >= _MAX_ARCHIVE_DEPTH:
        raise ValueError(f"archive nesting exceeds scan limit: {relative_path}")
    findings: list[str] = []
    unpacked = _bounded_gzip_decompress(data, budget)
    with tarfile.open(fileobj=BytesIO(unpacked), mode="r:") as archive:
        members = archive.getmembers()
        if len(members) > _MAX_ARCHIVE_MEMBERS:
            raise ValueError(f"archive has too many members: {relative_path}")
        if any(member.size > _MAX_ARCHIVE_UNCOMPRESSED_BYTES for member in members):
            raise ValueError(f"archive expands beyond scan limit: {relative_path}")
        for member in members:
            budget.charge_member()
            findings.extend(
                _tar_member_findings(
                    archive,
                    member,
                    relative_path,
                    private_name_digest,
                    approved_binary_digests,
                    forbidden_identifiers,
                    depth,
                    budget,
                )
            )
    return findings


def _bounded_gzip_decompress(data: bytes, budget: ArchiveBudget) -> bytes:
    """Decompress at most the reviewed archive budget plus one sentinel byte."""
    with gzip.GzipFile(fileobj=BytesIO(data)) as stream:
        limit = min(_MAX_ARCHIVE_UNCOMPRESSED_BYTES, budget.remaining_bytes)
        unpacked = stream.read(limit + 1)
    if len(unpacked) > limit:
        raise ValueError("gzip archive expands beyond scan limit")
    budget.charge_bytes(len(unpacked))
    return unpacked


def _tar_member_findings(
    archive: tarfile.TarFile,
    member: tarfile.TarInfo,
    relative_path: Path,
    private_name_digest: str,
    approved_binary_digests: Mapping[str, str],
    forbidden_identifiers: tuple[ForbiddenIdentifier, ...],
    depth: int,
    budget: ArchiveBudget,
) -> list[str]:
    findings = _archive_metadata_findings(
        "tar member metadata",
        (member.name, member.linkname, member.uname, member.gname),
        private_name_digest,
        forbidden_identifiers,
    )
    findings.extend(
        _archive_metadata_findings(
            "tar PAX metadata",
            tuple(member.pax_headers) + tuple(member.pax_headers.values()),
            private_name_digest,
            forbidden_identifiers,
        )
    )
    if member.isdir() or member.issym() or member.islnk():
        return findings
    if not member.isfile():
        raise ValueError("unsupported tar member type")
    extracted = archive.extractfile(member)
    if extracted is None:
        raise ValueError("archive member cannot be inspected")
    findings.extend(
        _data_findings(
            relative_path / member.name,
            _read_bounded(extracted, member.size),
            private_name_digest,
            approved_binary_digests,
            forbidden_identifiers,
            depth=depth + 1,
            budget=budget,
            charge_content=False,
        )
    )
    return findings


def _archive_metadata_findings(
    label: str,
    values: tuple[str, ...],
    private_name_digest: str,
    forbidden_identifiers: tuple[ForbiddenIdentifier, ...],
) -> list[str]:
    """Inspect archive metadata while returning only a safe field label."""
    found = any(
        _text_findings(
            Path("metadata"), value, private_name_digest, forbidden_identifiers
        )
        for value in values
        if value
    )
    return [f"{label}: forbidden identifier"] if found else []


def _read_bounded(
    stream: object, declared_size: int, remaining_budget: int | None = None
) -> bytes:
    """Read one member with both its declaration and the global budget enforced."""
    limit = min(declared_size, _MAX_ARCHIVE_UNCOMPRESSED_BYTES)
    if remaining_budget is not None:
        limit = min(limit, remaining_budget)
    data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("archive member exceeds declared or global limit")
    return data


def _zip_metadata_size(member: zipfile.ZipInfo) -> int:
    return (
        len(member.filename.encode("utf-8")) + len(member.comment) + len(member.extra)
    )


def _new_archive_budget() -> ArchiveBudget:
    return ArchiveBudget(
        remaining_bytes=_MAX_ARCHIVE_UNCOMPRESSED_BYTES,
        remaining_members=_MAX_ARCHIVE_MEMBERS,
    )


def _zip_member_supported(member: zipfile.ZipInfo) -> bool:
    mode = member.external_attr >> 16
    file_type = stat.S_IFMT(mode)
    return not file_type or member.is_dir() or stat.S_ISREG(mode)


def _archive_findings(
    relative_path: Path,
    data: bytes,
    private_name_digest: str,
    approved_binary_digests: Mapping[str, str],
    forbidden_identifiers: tuple[ForbiddenIdentifier, ...],
    depth: int,
    budget: ArchiveBudget,
) -> list[str]:
    """Inspect every bounded ZIP member rather than exempting the container."""
    if depth >= _MAX_ARCHIVE_DEPTH:
        raise ValueError(f"archive nesting exceeds scan limit: {relative_path}")
    findings: list[str] = []
    with zipfile.ZipFile(BytesIO(data)) as archive:
        budget.charge_bytes(len(archive.comment))
        findings.extend(
            _archive_metadata_findings(
                "ZIP archive comment",
                (archive.comment.decode("latin-1"),),
                private_name_digest,
                forbidden_identifiers,
            )
        )
        members = archive.infolist()
        if len(members) > _MAX_ARCHIVE_MEMBERS:
            raise ValueError(f"archive has too many members: {relative_path}")
        if any(
            member.file_size > _MAX_ARCHIVE_UNCOMPRESSED_BYTES for member in members
        ):
            raise ValueError(f"archive expands beyond scan limit: {relative_path}")
        for member in members:
            budget.charge_member()
            budget.charge_bytes(_zip_metadata_size(member))
            findings.extend(
                _archive_metadata_findings(
                    "ZIP member metadata",
                    (
                        member.filename,
                        member.comment.decode("latin-1"),
                        member.extra.decode("latin-1"),
                    ),
                    private_name_digest,
                    forbidden_identifiers,
                )
            )
            if not _zip_member_supported(member):
                raise ValueError("unsupported ZIP member type")
            if member.is_dir():
                continue
            if member.flag_bits & 0x1:
                raise ValueError(f"encrypted archive member: {relative_path}")
            member_path = relative_path / member.filename
            with archive.open(member) as stream:
                member_data = _read_bounded(
                    stream, member.file_size, budget.remaining_bytes
                )
            member_findings = _data_findings(
                member_path,
                member_data,
                private_name_digest,
                approved_binary_digests,
                forbidden_identifiers,
                depth=depth + 1,
                budget=budget,
                charge_content=True,
            )
            findings.extend(member_findings)
    return findings


def _data_findings(
    relative_path: Path,
    data: bytes,
    private_name_digest: str,
    approved_binary_digests: Mapping[str, str],
    forbidden_identifiers: tuple[ForbiddenIdentifier, ...] = _FORBIDDEN_IDENTIFIERS,
    *,
    depth: int = 0,
    budget: ArchiveBudget | None = None,
    charge_content: bool = False,
) -> list[str]:
    """Inspect one blob, validating binary content and failing closed on text."""
    if budget is not None and charge_content:
        budget.charge_bytes(len(data))
    binary_kind = _recognized_binary_kind(relative_path, data)
    binary_findings = _binary_findings(
        binary_kind,
        relative_path,
        data,
        private_name_digest,
        approved_binary_digests,
        forbidden_identifiers,
        depth,
        budget,
    )
    if binary_findings is not None:
        return binary_findings
    return _decoded_text_findings(
        relative_path, data, private_name_digest, forbidden_identifiers
    )


def _binary_findings(
    binary_kind: str | None,
    relative_path: Path,
    data: bytes,
    private_name_digest: str,
    approved_binary_digests: Mapping[str, str],
    forbidden_identifiers: tuple[ForbiddenIdentifier, ...],
    depth: int,
    budget: ArchiveBudget | None,
) -> list[str] | None:
    if binary_kind == "opaque":
        content_digest = hashlib.sha256(data).hexdigest()
        relative_name = relative_path.as_posix()
        if _approved_binary(relative_name, content_digest, approved_binary_digests):
            return []
        byte_findings = _text_findings(
            relative_path,
            data.decode("latin-1"),
            private_name_digest,
            forbidden_identifiers,
        )
        if byte_findings:
            return byte_findings
        raise ValueError(f"opaque binary is not digest-approved: {relative_path}")
    if binary_kind == "zip":
        budget = budget or _new_archive_budget()
        return _archive_findings(
            relative_path,
            data,
            private_name_digest,
            approved_binary_digests,
            forbidden_identifiers,
            depth,
            budget,
        )
    if binary_kind == "tar":
        budget = budget or _new_archive_budget()
        return _tar_findings(
            relative_path,
            data,
            private_name_digest,
            approved_binary_digests,
            forbidden_identifiers,
            depth,
            budget,
        )
    return None


def _decoded_text_findings(
    relative_path: Path,
    data: bytes,
    private_name_digest: str,
    forbidden_identifiers: tuple[ForbiddenIdentifier, ...],
) -> list[str]:
    normalized = data.replace(b"\0", b"")
    try:
        text = normalized.decode("utf-8")
    except UnicodeDecodeError as exc:
        byte_findings = _text_findings(
            relative_path,
            normalized.decode("latin-1"),
            private_name_digest,
            forbidden_identifiers,
        )
        if byte_findings:
            return byte_findings
        raise UnicodeError(f"tracked text is not valid UTF-8: {relative_path}") from exc
    return _text_findings(
        relative_path, text, private_name_digest, forbidden_identifiers
    )


def _approved_binary(
    relative_name: str,
    content_digest: str,
    approved_binary_digests: Mapping[str, str],
) -> bool:
    """Accept a reviewed binary at its tree path or beneath a package root."""
    return any(
        digest == content_digest
        and (relative_name == path or relative_name.endswith(f"/{path}"))
        for path, digest in approved_binary_digests.items()
    )


def violations(
    root: Path,
    private_name_digest: str = _PRIVATE_NAME_DIGEST,
    approved_binary_digests: Mapping[str, str] = _APPROVED_BINARY_DIGESTS,
    forbidden_identifiers: tuple[ForbiddenIdentifier, ...] = _FORBIDDEN_IDENTIFIERS,
) -> list[str]:
    """Return proposed-tree matches and fail if tracked content is unreadable."""
    findings: list[str] = []
    for entry in proposed_files(root):
        relative_path = entry.relative_path
        if _contains_private_name(
            str(relative_path), private_name_digest
        ) or _identifier_categories(str(relative_path), forbidden_identifiers):
            findings.append("tracked path metadata: forbidden identifier")
        findings.extend(
            _data_findings(
                relative_path,
                entry.data,
                private_name_digest,
                approved_binary_digests,
                forbidden_identifiers,
            )
        )
    return findings


def main(
    argv: list[str] | None = None,
    *,
    private_name_digest: str = _PRIVATE_NAME_DIGEST,
    approved_binary_digests: Mapping[str, str] = _APPROVED_BINARY_DIGESTS,
    forbidden_identifiers: tuple[ForbiddenIdentifier, ...] = _FORBIDDEN_IDENTIFIERS,
) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--artifact", action="append", type=Path, default=[])
    parser.add_argument("--artifacts-only", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.artifacts_only and not args.artifact:
            raise ValueError("artifact-only scan requires an artifact")
        findings = (
            []
            if args.artifacts_only
            else violations(
                args.root.resolve(),
                private_name_digest,
                approved_binary_digests,
                forbidden_identifiers,
            )
        )
        for artifact in args.artifact:
            artifact_name = artifact.name
            if _contains_private_name(
                artifact_name, private_name_digest
            ) or _identifier_categories(artifact_name, forbidden_identifiers):
                findings.append("artifact filename: forbidden identifier")
            findings.extend(
                _data_findings(
                    Path(artifact_name),
                    _read_artifact_bounded(artifact),
                    private_name_digest,
                    approved_binary_digests,
                    forbidden_identifiers,
                )
            )
    except (
        OSError,
        UnicodeError,
        subprocess.SubprocessError,
        tarfile.TarError,
        ValueError,
        zipfile.BadZipFile,
    ) as exc:
        print(
            f"public-boundary scan failed closed: {_safe_failure_reason(exc)}",
            file=sys.stderr,
        )
        return 2
    if findings:
        print("private control-plane references found:", file=sys.stderr)
        print("\n".join(findings), file=sys.stderr)
        return 1
    print("public-boundary scan passed")
    return 0


def _read_artifact_bounded(path: Path) -> bytes:
    """Reject oversized compressed input before allocating its full contents."""
    if path.stat().st_size > _MAX_ARCHIVE_COMPRESSED_BYTES:
        raise ValueError("artifact compressed input exceeds scan limit")
    with path.open("rb") as stream:
        data = stream.read(_MAX_ARCHIVE_COMPRESSED_BYTES + 1)
    if len(data) > _MAX_ARCHIVE_COMPRESSED_BYTES:
        raise ValueError("artifact compressed input exceeds scan limit")
    return data


def _safe_failure_reason(exc: BaseException) -> str:
    """Classify failures without echoing paths, metadata, or forbidden values."""
    message = str(exc).casefold()
    reasons = (
        ("cumulative byte budget", "cumulative-byte-budget"),
        ("cumulative member budget", "cumulative-member-budget"),
        ("compressed input", "compressed-input-limit"),
        ("expands beyond", "expanded-content-limit"),
        ("nesting exceeds", "archive-nesting-limit"),
        ("too many members", "archive-member-limit"),
        ("unsupported", "unsupported-archive-member"),
        ("not digest-approved", "unapproved-opaque-binary"),
        ("not valid utf-8", "invalid-text-encoding"),
        ("requires an artifact", "missing-artifact"),
    )
    return next(
        (reason for marker, reason in reasons if marker in message), type(exc).__name__
    )


if __name__ == "__main__":
    raise SystemExit(main())
