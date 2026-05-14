"""AST contracts for the DeletionRequest executor job."""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
EXECUTOR_PATH = (
    REPO_ROOT / "netbox_proxbox" / "intent" / "deletion_executor.py"
)


def _module() -> ast.Module:
    return ast.parse(EXECUTOR_PATH.read_text(encoding="utf-8"))


def test_executor_module_exposes_public_job_shape():
    module = _module()
    class_names = {
        node.name for node in ast.walk(module) if isinstance(node, ast.ClassDef)
    }
    assigned_names = {
        target.id
        for node in ast.walk(module)
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
    }
    assert "DeletionExecutorJob" in class_names
    assert "DELETION_EXECUTOR_JOB_TIMEOUT" in assigned_names


def test_executor_contains_backend_route_and_actor_header_literals():
    source = EXECUTOR_PATH.read_text(encoding="utf-8")
    assert "/intent/deletion-requests/" in source
    assert "X-Proxbox-Actor" in source


def test_executor_has_third_layer_self_approval_check():
    module = _module()
    comparisons = [node for node in ast.walk(module) if isinstance(node, ast.Compare)]
    assert any(
        isinstance(compare.left, ast.Attribute)
        and compare.left.attr == "authorizer_id"
        and any(
            isinstance(comparator, ast.Attribute)
            and comparator.attr == "requested_by_id"
            for comparator in compare.comparators
        )
        for compare in comparisons
    )
