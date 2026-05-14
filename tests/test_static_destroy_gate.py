"""Package-wide static gate against direct Proxmox destroy calls."""

from __future__ import annotations

from pathlib import Path
import re

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_PATH = REPO_ROOT / "netbox_proxbox"

FORBIDDEN_LITERAL_PATTERNS = (
    ".qemu.delete(",
    ".lxc.delete(",
    "qemu_destroy",
    "lxc_destroy",
)
FORBIDDEN_REGEX_PATTERNS = (
    re.compile(r"requests\.delete\(.*qemu", re.DOTALL),
    re.compile(r"requests\.delete\(.*lxc", re.DOTALL),
)


def _python_sources() -> list[Path]:
    paths: list[Path] = []
    for path in PACKAGE_PATH.rglob("*.py"):
        relative_parts = path.relative_to(PACKAGE_PATH).parts
        if "migrations" in relative_parts or "static" in relative_parts:
            continue
        paths.append(path)
    return paths


def test_plugin_never_calls_proxmox_destroy_directly():
    for path in _python_sources():
        source = path.read_text(encoding="utf-8")
        for fragment in FORBIDDEN_LITERAL_PATTERNS:
            assert fragment not in source, f"{path} contains forbidden {fragment!r}"
        for pattern in FORBIDDEN_REGEX_PATTERNS:
            assert not pattern.search(source), (
                f"{path} contains forbidden pattern {pattern.pattern!r}"
            )
