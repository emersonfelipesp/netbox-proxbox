"""AST contract test for the initial netbox_ceph migration.

Pins the v1 schema shape without loading Django: the migration must
declare all nine plugin model tables, depend on the matching
``netbox_proxbox`` initial migration, and namespace every
``UniqueConstraint`` under the ``netbox_ceph_*`` prefix to avoid
collisions with sibling plugins.
"""

from __future__ import annotations

import ast
import pathlib


REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
MIGRATION_PATH = (
    REPO_ROOT
    / "netbox_ceph"
    / "netbox_ceph"
    / "migrations"
    / "0001_initial.py"
)


EXPECTED_MODELS = {
    "CephPluginSettings",
    "CephCluster",
    "CephDaemon",
    "CephOSD",
    "CephPool",
    "CephFilesystem",
    "CephCrushRule",
    "CephFlag",
    "CephHealthCheck",
}


def _migration_source() -> str:
    return MIGRATION_PATH.read_text(encoding="utf-8")


def test_migration_file_exists() -> None:
    assert MIGRATION_PATH.is_file()


def test_migration_declares_all_model_tables() -> None:
    tree = ast.parse(_migration_source())
    declared: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        is_create_model = (
            isinstance(func, ast.Attribute) and func.attr == "CreateModel"
        )
        if not is_create_model:
            continue
        for kw in node.keywords:
            if kw.arg == "name" and isinstance(kw.value, ast.Constant):
                declared.add(str(kw.value.value))
    assert declared == EXPECTED_MODELS, declared


def test_migration_depends_on_netbox_proxbox() -> None:
    source = _migration_source()
    assert '"netbox_proxbox"' in source
    assert '"extras"' in source


def test_unique_constraint_names_are_namespaced() -> None:
    tree = ast.parse(_migration_source())
    seen: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        is_unique_constraint = (
            isinstance(func, ast.Attribute) and func.attr == "UniqueConstraint"
        )
        if not is_unique_constraint:
            continue
        for kw in node.keywords:
            if kw.arg == "name" and isinstance(kw.value, ast.Constant):
                seen.append(str(kw.value.value))
    assert seen, "migration declares no UniqueConstraint names"
    for name in seen:
        assert name.startswith("netbox_ceph_"), name
