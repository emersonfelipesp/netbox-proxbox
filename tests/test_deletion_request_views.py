"""AST contracts for DeletionRequest UI views and routes."""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
VIEW_PATH = REPO_ROOT / "netbox_proxbox" / "views" / "deletion_requests.py"
URLS_PATH = REPO_ROOT / "netbox_proxbox" / "urls.py"


def _module() -> ast.Module:
    return ast.parse(VIEW_PATH.read_text(encoding="utf-8"))


def test_deletion_request_views_parse_cleanly():
    assert isinstance(_module(), ast.Module)


def test_deletion_request_views_expose_four_view_classes():
    class_names = {
        node.name for node in ast.walk(_module()) if isinstance(node, ast.ClassDef)
    }
    assert {
        "DeletionRequestListView",
        "DeletionRequestView",
        "DeletionRequestApproveView",
        "DeletionRequestRejectView",
    } <= class_names


def test_urls_register_deletion_requests_literal():
    source = URLS_PATH.read_text(encoding="utf-8")
    assert "deletion-requests" in source
