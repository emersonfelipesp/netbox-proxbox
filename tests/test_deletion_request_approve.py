"""AST contracts for DeletionRequest approval wiring."""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FORM_PATH = (
    REPO_ROOT
    / "netbox_proxbox"
    / "forms"
    / "deletion_request_approve.py"
)
VIEW_PATH = REPO_ROOT / "netbox_proxbox" / "views" / "deletion_requests.py"

SELF_APPROVAL_MESSAGE = (
    "Self-approval blocked: a different authorized user must approve this request."
)


def test_approve_form_declares_vmid_field():
    module = ast.parse(FORM_PATH.read_text(encoding="utf-8"))
    form_class = next(
        (
            node
            for node in ast.walk(module)
            if isinstance(node, ast.ClassDef)
            and node.name == "DeletionRequestApproveForm"
        ),
        None,
    )
    assert form_class is not None
    assert any(
        isinstance(stmt, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "vmid" for target in stmt.targets)
        for stmt in form_class.body
    )


def test_approve_view_contains_self_approval_403_literal():
    source = VIEW_PATH.read_text(encoding="utf-8")
    assert SELF_APPROVAL_MESSAGE in source
