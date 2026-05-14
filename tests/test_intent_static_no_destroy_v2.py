"""Static guardrail: intent work must not call Proxmox destroy primitives."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_PATH = REPO_ROOT / "netbox_proxbox"


def test_netbox_proxbox_source_contains_no_proxmox_destroy_calls():
    forbidden = (
        ".qemu.delete(",
        ".lxc.delete(",
        "qemu_destroy",
        "lxc_destroy",
    )
    for path in PACKAGE_PATH.rglob("*.py"):
        relative_parts = path.relative_to(PACKAGE_PATH).parts
        if "migrations" in relative_parts or "static" in relative_parts:
            continue

        source = path.read_text(encoding="utf-8")
        for fragment in forbidden:
            assert fragment not in source, f"{path} contains forbidden {fragment!r}"
