"""AST contract for the full DeletionRequest safe-delete schema."""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = REPO_ROOT / "netbox_proxbox" / "models" / "deletion_request.py"


def _module() -> ast.Module:
    return ast.parse(MODEL_PATH.read_text(encoding="utf-8"))


def _class(module: ast.Module, name: str) -> ast.ClassDef:
    for node in ast.walk(module):
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    raise AssertionError(f"{name} class not found")


def _class_assignments(class_def: ast.ClassDef) -> set[str]:
    assigned: set[str] = set()
    for node in class_def.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                assigned.add(target.id)
    return assigned


def test_deletion_request_declares_required_schema_fields():
    deletion_request = _class(_module(), "DeletionRequest")
    assignments = _class_assignments(deletion_request)
    expected = {
        "branch",
        "requested_by",
        "authorizer",
        "state",
        "vmid",
        "node",
        "kind",
        "metadata_snapshot",
        "reject_reason",
        "executor_run_uuid",
        "requested_at",
        "approved_at",
        "executed_at",
    }
    assert expected <= assignments


def test_deletion_request_state_textchoices_are_complete():
    deletion_request = _class(_module(), "DeletionRequest")
    state_class = next(
        (
            node
            for node in deletion_request.body
            if isinstance(node, ast.ClassDef) and node.name.lower() == "state"
        ),
        None,
    )
    assert state_class is not None, "DeletionRequest must define a State class"
    assert any(
        (isinstance(base, ast.Attribute) and base.attr == "TextChoices")
        or (isinstance(base, ast.Name) and base.id == "TextChoices")
        for base in state_class.bases
    )

    members = {name.upper() for name in _class_assignments(state_class)}
    assert {
        "PENDING",
        "APPROVED",
        "REJECTED",
        "EXECUTING",
        "SUCCEEDED",
        "FAILED",
    } <= members


def test_deletion_request_meta_keeps_authorization_permission():
    deletion_request = _class(_module(), "DeletionRequest")
    meta = next(
        (
            node
            for node in deletion_request.body
            if isinstance(node, ast.ClassDef) and node.name == "Meta"
        ),
        None,
    )
    assert meta is not None, "DeletionRequest.Meta must exist"
    constants = {
        node.value
        for node in ast.walk(meta)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    assert "authorize_deletion_request" in constants
