"""Source-contract tests for the cluster-wide HA view (issue #243)."""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
HA_PATH = REPO_ROOT / "netbox_proxbox" / "views" / "ha.py"
URLS_PATH = REPO_ROOT / "netbox_proxbox" / "urls.py"
NAV_PATH = REPO_ROOT / "netbox_proxbox" / "navigation.py"


def _find_class(module: ast.Module, name: str) -> ast.ClassDef:
    for node in ast.walk(module):
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    raise AssertionError(f"class {name} not found")


def test_ha_cluster_view_class_exists_and_has_template():
    module = ast.parse(HA_PATH.read_text(encoding="utf-8"))
    cls = _find_class(module, "HAClusterView")
    base_names = {
        b.attr if isinstance(b, ast.Attribute) else getattr(b, "id", "")
        for b in cls.bases
    }
    assert "View" in base_names
    template_value: ast.AST | None = None
    for node in cls.body:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == "template_name":
                    template_value = node.value
    assert isinstance(template_value, ast.Constant)
    assert template_value.value == "netbox_proxbox/ha.html"


def test_ha_cluster_view_calls_summary_endpoint():
    source = HA_PATH.read_text(encoding="utf-8")
    assert "/proxmox/cluster/ha/summary" in source
    assert "get_fastapi_request_context" in source
    assert "translate_request_exception" in source


def test_urls_register_ha_route_with_expected_name():
    source = URLS_PATH.read_text(encoding="utf-8")
    assert 'path("ha/"' in source
    assert "HAClusterView" in source
    assert 'name="ha"' in source


def test_navigation_includes_ha_menu_item():
    source = NAV_PATH.read_text(encoding="utf-8")
    assert "plugins:netbox_proxbox:ha" in source
    assert "HA Status" in source
