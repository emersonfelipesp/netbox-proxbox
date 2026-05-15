"""AST contract that apply jobs emit audit-visible log lines."""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
APPLY_JOB_PATH = REPO_ROOT / "netbox_proxbox" / "intent" / "apply_job.py"
LOGGER_METHODS = {"info", "warning", "error"}


def _module() -> ast.Module:
    return ast.parse(APPLY_JOB_PATH.read_text(encoding="utf-8"))


def _class(module: ast.Module, name: str) -> ast.ClassDef:
    for node in ast.walk(module):
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    raise AssertionError(f"{name} class not found")


def _method(class_def: ast.ClassDef, name: str) -> ast.FunctionDef:
    for node in class_def.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{class_def.name}.{name}() not found")


def test_apply_job_run_contains_logger_calls():
    run_method = _method(_class(_module(), "ProxmoxApplyJob"), "run")
    logger_calls = [
        node
        for node in ast.walk(run_method)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "logger"
        and node.func.attr in LOGGER_METHODS
    ]
    assert logger_calls, "ProxmoxApplyJob.run() must keep audit-visible logging"
