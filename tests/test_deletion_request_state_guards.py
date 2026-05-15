"""AST contracts for the DeletionRequest workflow state guards.

These guards close a four-eyes workflow gap where a holder of
``authorize_deletion_request`` could re-approve a previously rejected
request, or re-trigger an already-executed request, because no layer
enforced the state precondition before mutating the record or
dispatching the executor RQ job.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
VIEW_PATH = REPO_ROOT / "netbox_proxbox" / "views" / "deletion_requests.py"
EXECUTOR_PATH = REPO_ROOT / "netbox_proxbox" / "intent" / "deletion_executor.py"

NON_PENDING_LITERAL = (
    "Deletion request is not pending; approve and reject are only valid in the pending state."
)


def _module(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _post_handler(class_name: str) -> ast.FunctionDef:
    module = _module(VIEW_PATH)
    view = next(
        node
        for node in ast.walk(module)
        if isinstance(node, ast.ClassDef) and node.name == class_name
    )
    for node in view.body:
        if isinstance(node, ast.FunctionDef) and node.name == "post":
            return node
    raise AssertionError(f"{class_name} must define a post() handler")


def _post_handler_has_pending_state_guard(class_name: str) -> bool:
    handler = _post_handler(class_name)
    for node in ast.walk(handler):
        if not isinstance(node, ast.Compare):
            continue
        if not isinstance(node.left, ast.Attribute) or node.left.attr != "state":
            continue
        if not any(isinstance(op, ast.NotEq) for op in node.ops):
            continue
        if any(
            isinstance(comparator, ast.Attribute) and comparator.attr == "PENDING"
            for comparator in node.comparators
        ):
            return True
    return False


def test_non_pending_state_message_is_declared():
    assert NON_PENDING_LITERAL in VIEW_PATH.read_text(encoding="utf-8")


def test_approve_view_blocks_non_pending_states():
    assert _post_handler_has_pending_state_guard("DeletionRequestApproveView")


def test_reject_view_blocks_non_pending_states():
    assert _post_handler_has_pending_state_guard("DeletionRequestRejectView")


def test_executor_aborts_when_state_is_not_approved():
    executor_module = _module(EXECUTOR_PATH)
    run_method = next(
        node
        for node in ast.walk(executor_module)
        if isinstance(node, ast.FunctionDef) and node.name == "run"
    )
    for node in ast.walk(run_method):
        if not isinstance(node, ast.Compare):
            continue
        if not isinstance(node.left, ast.Attribute) or node.left.attr != "state":
            continue
        if not any(isinstance(op, ast.NotEq) for op in node.ops):
            continue
        if any(
            isinstance(comparator, ast.Attribute) and comparator.attr == "APPROVED"
            for comparator in node.comparators
        ):
            return
    raise AssertionError(
        "DeletionExecutorJob.run() must abort when state != State.APPROVED"
    )
