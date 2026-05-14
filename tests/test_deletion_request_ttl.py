"""AST contracts for DeletionRequest TTL cleanup."""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TTL_PATH = REPO_ROOT / "netbox_proxbox" / "intent" / "deletion_ttl_cron.py"


def test_ttl_module_exposes_auto_reject_function():
    module = ast.parse(TTL_PATH.read_text(encoding="utf-8"))
    function_names = {
        node.name for node in ast.walk(module) if isinstance(node, ast.FunctionDef)
    }
    assert "auto_reject_expired_deletion_requests" in function_names


def test_ttl_source_contains_rejection_literal():
    source = TTL_PATH.read_text(encoding="utf-8")
    assert '"TTL"' in source
