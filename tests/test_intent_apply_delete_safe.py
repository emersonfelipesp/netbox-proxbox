"""Sub-PR H (#385): source contract for DELETE safe-delete dispatch."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
APPLY_JOB_PATH = REPO_ROOT / "netbox_proxbox" / "intent" / "apply_job.py"
INTENT_PATH = REPO_ROOT / "netbox_proxbox" / "intent"


def test_apply_job_contains_safe_delete_dispatch_literals():
    source = APPLY_JOB_PATH.read_text(encoding="utf-8")
    for literal in (
        "DeletionRequest",
        "delete-pending-approval",
        "netbox_proxbox.intent_delete_vm",
        "netbox_proxbox.intent_delete_lxc",
        "apply_destroy_confirmed",
    ):
        assert literal in source


def test_intent_package_contains_no_destroy_calls():
    forbidden = (
        "qemu_destroy",
        "proxmox.delete",
        ".qemu.delete(",
        ".lxc.delete(",
    )
    for path in INTENT_PATH.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        for fragment in forbidden:
            assert fragment not in source, f"{path} contains forbidden {fragment!r}"
