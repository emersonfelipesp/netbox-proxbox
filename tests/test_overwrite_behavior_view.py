"""Contract tests for the ProxmoxEndpoint Overwrite Behavior tab.

The former detail-page "Sync Overwrite Behavior" card was moved to a dedicated
read-only ``ObjectView`` tab that splits the ``overwrite_*`` flags into
per-category sub-tabs mirroring ``OVERWRITE_FIELD_GROUPS``.
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PROXMOX_VIEW_PATH = REPO_ROOT / "netbox_proxbox" / "views" / "endpoints" / "proxmox.py"
CONSTANTS_PATH = REPO_ROOT / "netbox_proxbox" / "constants.py"
TEMPLATE_DIR = REPO_ROOT / "netbox_proxbox" / "templates" / "netbox_proxbox"


@pytest.fixture(scope="module")
def view_module_ast() -> ast.Module:
    return ast.parse(PROXMOX_VIEW_PATH.read_text(encoding="utf-8"))


def _find_class(module: ast.Module, name: str) -> ast.ClassDef:
    for node in ast.walk(module):
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    raise AssertionError(f"class {name} not found")


def _find_assign(module: ast.Module, target: str) -> ast.AST | None:
    for node in module.body:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == target:
                    return node.value
    return None


# ── View contract ────────────────────────────────────────────────────────────


def test_view_is_object_view_in_public_all(view_module_ast):
    cls = _find_class(view_module_ast, "ProxmoxEndpointOverwriteBehaviorView")
    base_names = {
        b.attr if isinstance(b, ast.Attribute) else getattr(b, "id", "")
        for b in cls.bases
    }
    assert "ObjectView" in base_names

    public = _find_assign(view_module_ast, "__all__")
    assert public is not None
    elts = {e.value for e in public.elts if isinstance(e, ast.Constant)}
    assert "ProxmoxEndpointOverwriteBehaviorView" in elts


def test_view_registered_at_overwrite_behavior_path(view_module_ast):
    cls = _find_class(view_module_ast, "ProxmoxEndpointOverwriteBehaviorView")
    paths: list[str] = []
    for deco in cls.decorator_list:
        if isinstance(deco, ast.Call) and (
            isinstance(deco.func, ast.Name) and deco.func.id == "register_model_view"
        ):
            for kw in deco.keywords:
                if kw.arg == "path" and isinstance(kw.value, ast.Constant):
                    paths.append(kw.value.value)
    assert "overwrite-behavior" in paths


def test_view_tab_metadata_and_template(view_module_ast):
    cls = _find_class(view_module_ast, "ProxmoxEndpointOverwriteBehaviorView")
    tab = next(
        (
            n.value
            for n in cls.body
            if isinstance(n, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "tab" for t in n.targets)
        ),
        None,
    )
    assert isinstance(tab, ast.Call) and isinstance(tab.func, ast.Name)
    assert tab.func.id == "ViewTab"
    kw = {k.arg: k.value for k in tab.keywords}
    assert (
        isinstance(kw["label"], ast.Constant)
        and kw["label"].value == "Overwrite Behavior"
    )
    assert kw["permission"].value == "netbox_proxbox.view_proxmoxendpoint"
    assert isinstance(kw["weight"].value, int)

    template = next(
        (
            n.value
            for n in cls.body
            if isinstance(n, ast.Assign)
            and any(
                isinstance(t, ast.Name) and t.id == "template_name" for t in n.targets
            )
        ),
        None,
    )
    assert isinstance(template, ast.Constant)
    assert template.value == "netbox_proxbox/proxmoxendpoint_overwrite_behavior.html"


def test_view_exposes_overwrite_row_groups(view_module_ast):
    cls = _find_class(view_module_ast, "ProxmoxEndpointOverwriteBehaviorView")
    method = next(
        (
            n
            for n in cls.body
            if isinstance(n, ast.FunctionDef) and n.name == "get_extra_context"
        ),
        None,
    )
    assert method is not None
    keys = {
        k.value
        for node in ast.walk(method)
        if isinstance(node, ast.Dict)
        for k in node.keys
        if isinstance(k, ast.Constant)
    }
    assert "overwrite_row_groups" in keys


def test_detail_view_no_longer_builds_overwrite_rows(view_module_ast):
    """The detail ObjectView must not still expose the flat ``overwrite_rows``."""
    cls = _find_class(view_module_ast, "ProxmoxEndpointView")
    src = ast.get_source_segment(PROXMOX_VIEW_PATH.read_text(encoding="utf-8"), cls)
    assert "overwrite_rows" not in (src or "")


# ── Grouping covers every overwrite field, in order ──────────────────────────


def test_row_groups_cover_all_overwrite_fields_in_order():
    spec = importlib.util.spec_from_file_location("_constants_ob", CONSTANTS_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    flat = tuple(
        field for _label, fields in mod.OVERWRITE_FIELD_GROUPS for field in fields
    )
    assert flat == mod.OVERWRITE_FIELDS
    assert len(flat) == 25


# ── Templates ────────────────────────────────────────────────────────────────


def test_overwrite_behavior_template_uses_subtabs():
    tpl = (TEMPLATE_DIR / "proxmoxendpoint_overwrite_behavior.html").read_text()
    assert "extends 'generic/object.html'" in tpl
    assert 'class="nav nav-tabs' in tpl
    assert "overwrite_row_groups" in tpl
    assert 'data-bs-target="#overwrite-behavior-pane-' in tpl
    # First sub-tab active, badges preserved.
    assert "show active" in tpl
    assert (
        "text-bg-success" in tpl and "text-bg-warning" in tpl and "text-bg-light" in tpl
    )


def test_detail_template_no_longer_has_overwrite_card():
    tpl = (TEMPLATE_DIR / "proxmoxendpoint.html").read_text()
    assert "Sync Overwrite Behavior" not in tpl
    assert "overwrite_rows" not in tpl
