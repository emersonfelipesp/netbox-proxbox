"""AST contract tests for the Sub-PR G UPDATE dispatch wiring."""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PAYLOAD_PATH = REPO_ROOT / "netbox_proxbox" / "intent" / "payload.py"
APPLY_JOB_PATH = REPO_ROOT / "netbox_proxbox" / "intent" / "apply_job.py"


def _module(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _function_def(module: ast.Module, name: str) -> ast.FunctionDef | None:
    for node in ast.walk(module):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def test_build_update_delta_is_defined_with_two_positional_args():
    module = _module(PAYLOAD_PATH)
    func = _function_def(module, "build_update_delta")
    assert func is not None, "build_update_delta must be defined in payload.py"

    args = func.args
    assert args.vararg is None
    assert args.kwarg is None
    assert len(args.kwonlyargs) == 0
    positional = [a.arg for a in args.args]
    assert positional[:2] == ["vm", "prev_state"], (
        f"build_update_delta(vm, prev_state) expected, got {positional}"
    )


def test_apply_job_imports_build_update_delta():
    module = _module(APPLY_JOB_PATH)
    found = False
    for node in ast.walk(module):
        if isinstance(node, ast.ImportFrom) and node.module == (
            "netbox_proxbox.intent.payload"
        ):
            for alias in node.names:
                if alias.name == "build_update_delta":
                    found = True
                    break
    assert found, (
        "apply_job.py must import build_update_delta from "
        "netbox_proxbox.intent.payload"
    )


def test_apply_job_dispatches_update_op():
    source = APPLY_JOB_PATH.read_text(encoding="utf-8")
    assert '"update"' in source, (
        "apply_job.py must reference the 'update' op literal for Sub-PR G"
    )
    assert "intent_update_vm" in source, (
        "apply_job.py must reference netbox_proxbox.intent_update_vm permission"
    )
    assert "intent_update_lxc" in source, (
        "apply_job.py must reference netbox_proxbox.intent_update_lxc permission"
    )
    assert "build_update_delta" in source, (
        "apply_job.py must call build_update_delta for UPDATE diffs"
    )
