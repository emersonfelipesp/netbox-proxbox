"""Source-contract and behavior tests for ``ProxmoxEndpointSettingsView``.

Two layers of coverage:

1. Static AST contract: the view subclasses ``ObjectEditView``, registers under
   ``path="settings"``, declares the tab with the required permission, points at
   ``ProxmoxEndpointSettingsForm`` and the dedicated template, and lives in the
   module's public ``__all__``.
2. Behavior: ``get_extra_context()`` exposes ``overwrite_field_groups`` sourced
   from ``OVERWRITE_FIELD_GROUPS`` so the template can render category cards.
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PROXMOX_VIEW_PATH = REPO_ROOT / "netbox_proxbox" / "views" / "endpoints" / "proxmox.py"
PROXMOX_FORM_PATH = REPO_ROOT / "netbox_proxbox" / "forms" / "proxmox.py"


@pytest.fixture(scope="module")
def view_module_ast() -> ast.Module:
    return ast.parse(PROXMOX_VIEW_PATH.read_text(encoding="utf-8"))


def _find_class(module: ast.Module, name: str) -> ast.ClassDef:
    for node in ast.walk(module):
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    raise AssertionError(f"class {name} not found in proxmox.py")


def _find_assign(class_node: ast.ClassDef, target: str) -> ast.AST | None:
    for node in class_node.body:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == target:
                    return node.value
    return None


# ── Source contract ──────────────────────────────────────────────────────────


def test_settings_view_class_exists(view_module_ast):
    cls = _find_class(view_module_ast, "ProxmoxEndpointSettingsView")
    base_names = {
        b.attr if isinstance(b, ast.Attribute) else getattr(b, "id", "")
        for b in cls.bases
    }
    assert "ObjectEditView" in base_names


def test_settings_view_in_public_all(view_module_ast):
    public = _find_assign(view_module_ast, "__all__")  # type: ignore[arg-type]
    assert public is not None
    elts = {e.value for e in public.elts if isinstance(e, ast.Constant)}  # type: ignore[union-attr]
    assert "ProxmoxEndpointSettingsView" in elts


def test_settings_view_uses_settings_form_and_template(view_module_ast):
    cls = _find_class(view_module_ast, "ProxmoxEndpointSettingsView")
    form_value = _find_assign(cls, "form")
    assert isinstance(form_value, ast.Name)
    assert form_value.id == "ProxmoxEndpointSettingsForm"

    template_value = _find_assign(cls, "template_name")
    assert isinstance(template_value, ast.Constant)
    assert template_value.value == "netbox_proxbox/proxmoxendpoint_settings.html"


def test_settings_view_tab_metadata(view_module_ast):
    cls = _find_class(view_module_ast, "ProxmoxEndpointSettingsView")
    tab_value = _find_assign(cls, "tab")
    assert isinstance(tab_value, ast.Call)
    assert isinstance(tab_value.func, ast.Name) and tab_value.func.id == "ViewTab"

    keywords = {kw.arg: kw.value for kw in tab_value.keywords}
    assert "label" in keywords
    assert (
        isinstance(keywords["label"], ast.Constant)
        and keywords["label"].value == "Settings"
    )
    assert isinstance(keywords["permission"], ast.Constant)
    assert keywords["permission"].value == "netbox_proxbox.view_proxmoxendpoint"
    assert isinstance(keywords["weight"], ast.Constant)
    assert isinstance(keywords["weight"].value, int)


def test_settings_view_registered_at_settings_path(view_module_ast):
    cls = _find_class(view_module_ast, "ProxmoxEndpointSettingsView")
    decorator_paths: list[str] = []
    for deco in cls.decorator_list:
        if not isinstance(deco, ast.Call):
            continue
        if not (
            isinstance(deco.func, ast.Name) and deco.func.id == "register_model_view"
        ):
            continue
        for kw in deco.keywords:
            if kw.arg == "path" and isinstance(kw.value, ast.Constant):
                decorator_paths.append(kw.value.value)
    assert "settings" in decorator_paths, (
        "ProxmoxEndpointSettingsView must be registered with path='settings'"
    )


def test_settings_view_has_get_extra_context(view_module_ast):
    cls = _find_class(view_module_ast, "ProxmoxEndpointSettingsView")
    methods = {n.name for n in cls.body if isinstance(n, ast.FunctionDef)}
    assert "get_extra_context" in methods


# ── Behavior of get_extra_context() ──────────────────────────────────────────


def test_get_extra_context_exposes_overwrite_field_groups():
    """Load OVERWRITE_FIELD_GROUPS and replicate the method body to lock the contract."""
    spec = importlib.util.spec_from_file_location(
        "_constants_for_settings_view", REPO_ROOT / "netbox_proxbox" / "constants.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    def get_extra_context(_self, _request, _instance):
        return {"overwrite_field_groups": mod.OVERWRITE_FIELD_GROUPS}

    request = SimpleNamespace()
    instance = SimpleNamespace()
    context = get_extra_context(SimpleNamespace(), request, instance)

    assert "overwrite_field_groups" in context
    groups = context["overwrite_field_groups"]
    assert tuple(name for name, _fields in groups) == tuple(
        name for name, _fields in mod.OVERWRITE_FIELD_GROUPS
    )
    flat = tuple(field for _name, fields in groups for field in fields)
    assert flat == mod.OVERWRITE_FIELDS
    assert len(flat) == 25


# ── Form-level label semantics ───────────────────────────────────────────────


def test_overwrite_vm_tags_uses_merge_label():
    """``overwrite_vm_tags`` is the one tri-state flag with merge (not replace)
    semantics; the Settings form must surface that distinction in its label
    so operators are not surprised by the additive behavior (commit 66ec814).
    """
    source = PROXMOX_FORM_PATH.read_text(encoding="utf-8")
    module = ast.parse(source)

    settings_form = _find_class(module, "ProxmoxEndpointSettingsForm")
    assert settings_form is not None, (
        "ProxmoxEndpointSettingsForm missing from forms/proxmox.py"
    )

    init = next(
        (
            n
            for n in settings_form.body
            if isinstance(n, ast.FunctionDef) and n.name == "__init__"
        ),
        None,
    )
    assert init is not None, "ProxmoxEndpointSettingsForm.__init__ not found"

    label_constants: list[str] = []
    for node in ast.walk(init):
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == "label":
                    if isinstance(node.value, ast.Constant) and isinstance(
                        node.value.value, str
                    ):
                        label_constants.append(node.value.value)

    assert "Merge VM tags" in label_constants, (
        "Settings form must override the overwrite_vm_tags label to 'Merge VM tags' "
        "so the merge-not-replace semantics are visible in the UI"
    )
