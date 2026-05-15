"""Sub-PR F (#383): ProxmoxApplyJob.run() must isolate per-diff failures."""

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
    raise AssertionError("run method not found")


def _changediff_for_loops(run: ast.FunctionDef) -> list[ast.For]:
    loops = []
    for node in ast.walk(run):
        if not isinstance(node, ast.For):
            continue
        if "changediff" in ast.unparse(node.iter).lower():
            loops.append(node)
    return loops


def test_changediff_loop_has_nested_try_except():
    run = _run_method(_parse())
    loops = _changediff_for_loops(run)
    assert loops, "run() must iterate the branch changediff collection"

    for loop in loops:
        assert any(isinstance(node, ast.Try) for node in ast.walk(loop)), (
            "each changediff loop must wrap per-diff work in try/except"
        )


def test_run_does_not_raise_after_changediff_loop():
    run = _run_method(_parse())
    for node in ast.walk(run):
        assert not isinstance(node, ast.Raise), (
            "run() must not raise after the per-VM loop or bubble per-diff failures"
        )
