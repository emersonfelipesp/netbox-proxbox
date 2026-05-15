"""AST contracts for four-eyes DeletionRequest authorization checks."""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
VIEW_PATH = REPO_ROOT / "netbox_proxbox" / "views" / "deletion_requests.py"
EXECUTOR_PATH = REPO_ROOT / "netbox_proxbox" / "intent" / "deletion_executor.py"
MODEL_PATH = REPO_ROOT / "netbox_proxbox" / "models" / "deletion_request.py"

SELF_APPROVAL_MESSAGE = (
    "Self-approval blocked: a different authorized user must approve this request."
)


def _module(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


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


def _attribute_name(node: ast.AST) -> str | None:
    return node.attr if isinstance(node, ast.Attribute) else None


def _has_authorizer_requested_by_comparison(node: ast.AST) -> bool:
    for compare in ast.walk(node):
        if not isinstance(compare, ast.Compare):
            continue
        names = {_attribute_name(compare.left)}
        names.update(_attribute_name(comparator) for comparator in compare.comparators)
        if {"authorizer_id", "requested_by_id"} <= names:
            return True
    return False


def _raises_validation_error(node: ast.AST) -> bool:
    for raise_node in ast.walk(node):
        if not isinstance(raise_node, ast.Raise):
            continue
        exc = raise_node.exc
        if isinstance(exc, ast.Call):
            func = exc.func
            if isinstance(func, ast.Name) and func.id == "ValidationError":
                return True
            if isinstance(func, ast.Attribute) and func.attr == "ValidationError":
                return True
    return False


def test_deletion_request_view_keeps_self_approval_message_literal():
    assert SELF_APPROVAL_MESSAGE in VIEW_PATH.read_text(encoding="utf-8")


def test_deletion_executor_rechecks_authorizer_is_not_requester():
    module = _module(EXECUTOR_PATH)
    run_method = _method(_class(module, "DeletionExecutorJob"), "run")
    assert _has_authorizer_requested_by_comparison(run_method)


def test_deletion_request_clean_rejects_self_approval():
    module = _module(MODEL_PATH)
    clean_method = _method(_class(module, "DeletionRequest"), "clean")
    assert _has_authorizer_requested_by_comparison(clean_method)
    assert _raises_validation_error(clean_method)
    constants = {
        node.value
        for node in ast.walk(clean_method)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    assert SELF_APPROVAL_MESSAGE in constants
