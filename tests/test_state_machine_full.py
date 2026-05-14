"""AST contracts for the intent apply and deletion state machines."""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DELETION_REQUEST_PATH = (
    REPO_ROOT / "netbox_proxbox" / "models" / "deletion_request.py"
)
APPLY_JOB_MODEL_PATH = REPO_ROOT / "netbox_proxbox" / "models" / "apply_job.py"


def _module(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _class(module: ast.Module, name: str) -> ast.ClassDef:
    for node in ast.walk(module):
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    raise AssertionError(f"{name} class not found")


def _state_members(model_path: Path, class_name: str) -> set[str]:
    model_class = _class(_module(model_path), class_name)
    state_class = next(
        (
            node
            for node in model_class.body
            if isinstance(node, ast.ClassDef) and node.name.lower() == "state"
        ),
        None,
    )
    assert state_class is not None, f"{class_name}.State must exist"

    members: set[str] = set()
    for node in state_class.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                members.add(target.id.upper())
    return members


def test_deletion_request_state_machine_is_complete():
    assert {
        "PENDING",
        "APPROVED",
        "REJECTED",
        "EXECUTING",
        "SUCCEEDED",
        "FAILED",
    } <= _state_members(DELETION_REQUEST_PATH, "DeletionRequest")


def test_proxmox_apply_job_state_machine_is_complete():
    assert {
        "QUEUED",
        "RUNNING",
        "SUCCEEDED",
        "FAILED",
        "PARTIAL",
    } <= _state_members(APPLY_JOB_MODEL_PATH, "ProxmoxApplyJob")
