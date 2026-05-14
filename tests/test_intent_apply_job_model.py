"""Sub-PR E (#382): AST contract for the full ProxmoxApplyJob model."""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = REPO_ROOT / "netbox_proxbox" / "models" / "apply_job.py"


def _parse() -> ast.Module:
    return ast.parse(MODEL_PATH.read_text(encoding="utf-8"))


def _apply_job_class() -> ast.ClassDef:
    for node in ast.walk(_parse()):
        if isinstance(node, ast.ClassDef) and node.name == "ProxmoxApplyJob":
            return node
    raise AssertionError("ProxmoxApplyJob class not found")


def test_apply_job_model_module_exposes_proxmox_apply_job():
    assert MODEL_PATH.exists(), "netbox_proxbox/models/apply_job.py must exist"
    assert _apply_job_class()


def test_apply_job_model_has_full_schema_fields():
    cls = _apply_job_class()
    assigned_names: set[str] = set()
    for stmt in cls.body:
        if isinstance(stmt, ast.Assign):
            assigned_names.update(
                target.id for target in stmt.targets if isinstance(target, ast.Name)
            )
        elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            assigned_names.add(stmt.target.id)

    for field_name in (
        "branch",
        "user",
        "run_uuid",
        "state",
        "per_vm_results",
        "started_at",
        "finished_at",
    ):
        assert field_name in assigned_names, f"{field_name} field is missing"


def test_apply_job_meta_permissions_are_preserved():
    cls = _apply_job_class()
    meta = next(
        (
            stmt
            for stmt in cls.body
            if isinstance(stmt, ast.ClassDef) and stmt.name == "Meta"
        ),
        None,
    )
    assert meta is not None, "ProxmoxApplyJob.Meta must exist"
    assert any(
        isinstance(stmt, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "permissions" for target in stmt.targets)
        for stmt in meta.body
    ), "ProxmoxApplyJob.Meta.permissions must be preserved"
