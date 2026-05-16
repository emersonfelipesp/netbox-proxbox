"""AST contract tests for ``netbox_ceph.CephConfig``.

Mirrors ``test_version.py`` for the sibling ``netbox_proxbox`` plugin so
the Ceph plugin metadata (version + NetBox compatibility window +
required plugin floor) stays in sync with releases without booting
Django.
"""

from __future__ import annotations

import ast
import pathlib

import pytest


REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
CEPH_INIT = REPO_ROOT / "netbox_ceph" / "netbox_ceph" / "__init__.py"


def _ceph_config_assignments() -> dict[str, object]:
    source = CEPH_INIT.read_text(encoding="utf-8")
    tree = ast.parse(source)
    found: dict[str, object] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or node.name != "CephConfig":
            continue
        for body in node.body:
            if not isinstance(body, ast.Assign):
                continue
            for target in body.targets:
                if isinstance(target, ast.Name) and isinstance(
                    body.value, ast.Constant
                ):
                    found[target.id] = body.value.value
                elif isinstance(target, ast.Name) and isinstance(
                    body.value, (ast.List, ast.Tuple)
                ):
                    values: list[object] = []
                    for elt in body.value.elts:
                        if isinstance(elt, ast.Constant):
                            values.append(elt.value)
                    found[target.id] = values
    return found


@pytest.fixture(scope="module")
def ceph_config_attrs() -> dict[str, object]:
    return _ceph_config_assignments()


def test_ceph_config_has_expected_identity(
    ceph_config_attrs: dict[str, object],
) -> None:
    assert ceph_config_attrs.get("name") == "netbox_ceph"
    assert ceph_config_attrs.get("base_url") == "ceph"


def test_ceph_config_requires_proxbox_plugin(
    ceph_config_attrs: dict[str, object],
) -> None:
    required = ceph_config_attrs.get("required_plugins")
    assert isinstance(required, list)
    assert "netbox_proxbox" in required


def test_ceph_config_netbox_compat_window(
    ceph_config_attrs: dict[str, object],
) -> None:
    """v1 must support the same NetBox window the sibling proxbox plugin does."""
    assert ceph_config_attrs.get("min_version") == "4.5.8"
    assert ceph_config_attrs.get("max_version") == "4.6.99"


def test_ceph_config_version_is_semver_string(
    ceph_config_attrs: dict[str, object],
) -> None:
    version = ceph_config_attrs.get("version")
    assert isinstance(version, str)
    parts = version.split(".")
    assert len(parts) == 3, f"expected 3-part version, got {version!r}"
    for part in parts:
        assert part.isdigit(), f"non-numeric segment in {version!r}"
