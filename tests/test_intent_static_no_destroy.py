"""Static safety check: intent code must not perform direct destroys."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
INTENT_DIR = REPO_ROOT / "netbox_proxbox" / "intent"
JOBS_PATH = REPO_ROOT / "netbox_proxbox" / "jobs.py"


def test_intent_code_contains_no_direct_destroy_patterns():
    forbidden = (
        "qemu_destroy",
        "lxc_destroy",
        ".delete_vm",
        "proxmox.delete",
    )

    paths = list(INTENT_DIR.rglob("*.py")) + [JOBS_PATH]
    for path in paths:
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        for fragment in forbidden:
            assert fragment not in text, (
                f"{path.relative_to(REPO_ROOT)} must not contain {fragment}"
            )
