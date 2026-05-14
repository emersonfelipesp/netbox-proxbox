"""Static contracts for stale pending-deletion tag cleanup."""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TTL_CRON_PATH = REPO_ROOT / "netbox_proxbox" / "intent" / "deletion_ttl_cron.py"
PROXMOX_TAGS_PATH = REPO_ROOT / "netbox_proxbox" / "intent" / "proxmox_tags.py"


def test_ttl_cleanup_removes_pending_deletion_tag():
    ttl_source = TTL_CRON_PATH.read_text(encoding="utf-8")
    tag_source = PROXMOX_TAGS_PATH.read_text(encoding="utf-8")
    assert "untag_pending_deletion" in ttl_source
    assert '"proxbox-pending-deletion"' in tag_source


def test_auto_reject_expired_deletion_requests_is_exported():
    module = ast.parse(TTL_CRON_PATH.read_text(encoding="utf-8"))
    function_names = {
        node.name for node in ast.walk(module) if isinstance(node, ast.FunctionDef)
    }
    assert "auto_reject_expired_deletion_requests" in function_names

    exported = {
        elt.value
        for node in module.body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name) and target.id == "__all__"
        if isinstance(node.value, ast.Tuple)
        for elt in node.value.elts
        if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
    }
    assert "auto_reject_expired_deletion_requests" in exported
