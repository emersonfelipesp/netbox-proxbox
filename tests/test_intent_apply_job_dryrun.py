"""Sub-PR E (#382): AST contract for the dry-run apply executor."""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
APPLY_JOB_PATH = REPO_ROOT / "netbox_proxbox" / "intent" / "apply_job.py"


def _parse() -> ast.Module:
    return ast.parse(APPLY_JOB_PATH.read_text(encoding="utf-8"))


def _class(module: ast.Module, name: str) -> ast.ClassDef:
    for node in ast.walk(module):
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    raise AssertionError(f"{name} class not found")


def test_apply_job_module_exposes_runner_and_timeout():
    assert APPLY_JOB_PATH.exists(), "netbox_proxbox/intent/apply_job.py must exist"
    module = _parse()
    assert _class(module, "ProxmoxApplyJob")
    assigned_names = {
        target.id
        for node in ast.iter_child_nodes(module)
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
    }
    assert "PROXBOX_APPLY_JOB_TIMEOUT" in assigned_names


def test_apply_job_executor_has_no_http_or_destroy_calls():
    text = APPLY_JOB_PATH.read_text(encoding="utf-8")
    forbidden_fragments = (
        "requests.post",
        "requests.delete",
        ".destroy(",
        "proxmox.delete",
    )
    for fragment in forbidden_fragments:
        assert fragment not in text, f"dry-run executor must not contain {fragment}"

    for node in ast.walk(_parse()):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in {"post", "delete"}:
            continue
        receiver = node.func.value
        assert not (
            isinstance(receiver, ast.Name) and receiver.id in {"requests", "proxmox"}
        ), "dry-run executor must not call requests/proxmox post/delete methods"


def test_enqueue_signature_includes_required_parameters():
    runner = _class(_parse(), "ProxmoxApplyJob")
    enqueue = next(
        (
            node
            for node in runner.body
            if isinstance(node, ast.FunctionDef) and node.name == "enqueue"
        ),
        None,
    )
    assert enqueue is not None, "ProxmoxApplyJob.enqueue classmethod not found"
    arg_names = [arg.arg for arg in enqueue.args.args + enqueue.args.kwonlyargs]
    for required in ("branch", "user", "run_uuid", "job_timeout"):
        assert required in arg_names, f"enqueue must accept {required}"
