"""Regression tests for SDN migration compatibility with supported NetBox versions."""

from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SDN_MIGRATION = (
    REPO_ROOT / "netbox_proxbox/migrations/0055_sdn_sync_controls_and_inventory.py"
)


def _migration_dependencies(path: Path) -> list[tuple[str, str]]:
    module = ast.parse(path.read_text(encoding="utf-8"))
    for node in module.body:
        if isinstance(node, ast.ClassDef) and node.name == "Migration":
            for statement in node.body:
                if not isinstance(statement, ast.Assign):
                    continue
                if any(
                    isinstance(target, ast.Name) and target.id == "dependencies"
                    for target in statement.targets
                ):
                    return ast.literal_eval(statement.value)
    raise AssertionError(f"Migration.dependencies not found in {path}")


def test_sdn_migration_uses_netbox_45_compatible_dependency_parents() -> None:
    dependencies = _migration_dependencies(SDN_MIGRATION)

    assert ("ipam", "0086_gfk_indexes") in dependencies
    assert ("vpn", "0011_add_comments_to_organizationalmodel") in dependencies
    assert ("ipam", "0089_default_ordering_indexes") not in dependencies
    assert ("vpn", "0012_default_ordering_indexes") not in dependencies
