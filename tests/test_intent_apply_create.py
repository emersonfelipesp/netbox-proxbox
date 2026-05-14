"""Sub-PR F (#383): source contract for CREATE apply dispatch."""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
APPLY_JOB_PATH = REPO_ROOT / "netbox_proxbox" / "intent" / "apply_job.py"


def _parse() -> ast.Module:
    return ast.parse(APPLY_JOB_PATH.read_text(encoding="utf-8"))


def _run_method(module: ast.Module) -> ast.FunctionDef:
    for node in ast.walk(module):
        if isinstance(node, ast.FunctionDef) and node.name == "run":
            return node
    raise AssertionError("ProxmoxApplyJob.run method not found")


def test_apply_job_targets_intent_apply_endpoint():
    text = APPLY_JOB_PATH.read_text(encoding="utf-8")
    assert "/intent/apply" in text


def test_apply_job_run_calls_posting_helper_and_module_posts():
    module = _parse()
    run = _run_method(module)

    run_calls = {
        node.func.id
        for node in ast.walk(run)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "_call_apply_endpoint" in run_calls

    assert any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "post"
        for node in ast.walk(module)
    )


def test_apply_job_imports_payload_builders():
    module = _parse()
    imported = set()
    for node in ast.walk(module):
        if (
            isinstance(node, ast.ImportFrom)
            and node.module == "netbox_proxbox.intent.payload"
        ):
            imported.update(alias.name for alias in node.names)

    assert "build_vm_payload" in imported
    assert "build_lxc_payload" in imported
