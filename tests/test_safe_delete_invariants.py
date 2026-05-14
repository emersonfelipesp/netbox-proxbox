"""Static guardrails for safe DELETE handling in the intent apply job."""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_PATH = REPO_ROOT / "netbox_proxbox"
APPLY_JOB_PATH = PACKAGE_PATH / "intent" / "apply_job.py"

DESTROY_LITERALS = (
    ".qemu.delete(",
    ".lxc.delete(",
    "qemu_destroy",
    "lxc_destroy",
)


def _contains_delete_compare(node: ast.AST) -> bool:
    for compare in ast.walk(node):
        if not isinstance(compare, ast.Compare):
            continue
        values = [compare.left, *compare.comparators]
        if any(
            isinstance(value, ast.Constant) and value.value == "delete"
            for value in values
        ):
            return True
    return False


def _python_sources() -> list[Path]:
    paths: list[Path] = []
    for path in PACKAGE_PATH.rglob("*.py"):
        relative_parts = path.relative_to(PACKAGE_PATH).parts
        if "migrations" in relative_parts or "static" in relative_parts:
            continue
        paths.append(path)
    return paths


def test_apply_job_delete_branch_creates_deletion_request_not_destroy():
    source = APPLY_JOB_PATH.read_text(encoding="utf-8")
    module = ast.parse(source)
    delete_branches = [
        ast.get_source_segment(source, node) or ""
        for node in ast.walk(module)
        if isinstance(node, ast.If) and _contains_delete_compare(node.test)
    ]
    assert delete_branches, "apply_job.py must branch on op == 'delete'"
    assert any("DeletionRequest" in branch for branch in delete_branches)

    for branch_source in delete_branches:
        for forbidden in DESTROY_LITERALS:
            assert forbidden not in branch_source


def test_netbox_proxbox_source_contains_no_direct_destroy_literals():
    for path in _python_sources():
        source = path.read_text(encoding="utf-8")
        for forbidden in DESTROY_LITERALS:
            assert forbidden not in source, f"{path} contains forbidden {forbidden!r}"
