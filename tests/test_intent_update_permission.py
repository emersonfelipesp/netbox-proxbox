"""AST contract test: UPDATE dispatch checks intent_update_* permissions."""

from __future__ import annotations

import ast
from pathlib import Path

APPLY_JOB_PATH = (
    Path(__file__).resolve().parents[1]
    / "netbox_proxbox"
    / "intent"
    / "apply_job.py"
)


def _find_run_method(module: ast.Module) -> ast.FunctionDef:
    for node in ast.walk(module):
        if isinstance(node, ast.ClassDef) and node.name == "ProxmoxApplyJob":
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "run":
                    return item
    raise AssertionError("ProxmoxApplyJob.run not found in apply_job.py")


def test_run_calls_has_perm_with_intent_update_literal():
    module = ast.parse(APPLY_JOB_PATH.read_text(encoding="utf-8"))
    run = _find_run_method(module)

    update_literals = {
        "netbox_proxbox.intent_update_vm",
        "netbox_proxbox.intent_update_lxc",
    }
    module_literals: set[str] = set()
    for node in ast.walk(module):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            module_literals.add(node.value)

    assert module_literals & update_literals, (
        "apply_job.py must reference at least one of "
        f"{update_literals}; found none"
    )

    has_perm_seen = False
    for node in ast.walk(run):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "has_perm":
                has_perm_seen = True
                break
            if isinstance(func, ast.Name) and func.id == "has_perm":
                has_perm_seen = True
                break
    assert has_perm_seen, "ProxmoxApplyJob.run must invoke has_perm() for RBAC"
