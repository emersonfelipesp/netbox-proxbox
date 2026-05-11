"""Source-contract tests for ``views.vm_ha.ProxmoxVMHATabView`` (issue #243)."""

from __future__ import annotations

import ast
from pathlib import Path

VM_HA_PATH = (
    Path(__file__).resolve().parents[1] / "netbox_proxbox" / "views" / "vm_ha.py"
)


def _module() -> ast.Module:
    return ast.parse(VM_HA_PATH.read_text(encoding="utf-8"))


def _find_class(module: ast.Module, name: str) -> ast.ClassDef:
    for node in ast.walk(module):
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    raise AssertionError(f"class {name} not found in vm_ha.py")


def _assign_value(cls: ast.ClassDef, target: str) -> ast.AST | None:
    for node in cls.body:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == target:
                    return node.value
    return None


def test_view_class_subclasses_object_view():
    cls = _find_class(_module(), "ProxmoxVMHATabView")
    base_names = {
        b.attr if isinstance(b, ast.Attribute) else getattr(b, "id", "")
        for b in cls.bases
    }
    assert "ObjectView" in base_names


def test_register_model_view_pins_path_and_name():
    cls = _find_class(_module(), "ProxmoxVMHATabView")
    register_call = next(
        (
            d
            for d in cls.decorator_list
            if isinstance(d, ast.Call)
            and isinstance(d.func, ast.Name)
            and d.func.id == "register_model_view"
        ),
        None,
    )
    assert register_call is not None
    assert isinstance(register_call.args[0], ast.Name)
    assert register_call.args[0].id == "VirtualMachine"
    assert isinstance(register_call.args[1], ast.Constant)
    assert register_call.args[1].value == "proxmox_ha"

    keywords = {kw.arg: kw.value for kw in register_call.keywords}
    assert "path" in keywords
    assert isinstance(keywords["path"], ast.Constant)
    assert keywords["path"].value == "proxmox-ha"


def test_view_uses_dedicated_template():
    cls = _find_class(_module(), "ProxmoxVMHATabView")
    template = _assign_value(cls, "template_name")
    assert isinstance(template, ast.Constant)
    assert template.value == "netbox_proxbox/vm_proxmox_ha.html"


def test_tab_metadata_uses_vm_view_permission():
    cls = _find_class(_module(), "ProxmoxVMHATabView")
    tab_value = _assign_value(cls, "tab")
    assert isinstance(tab_value, ast.Call)
    assert isinstance(tab_value.func, ast.Name) and tab_value.func.id == "ViewTab"
    keywords = {kw.arg: kw.value for kw in tab_value.keywords}
    assert isinstance(keywords["label"], ast.Constant)
    assert keywords["label"].value == "HA"
    assert isinstance(keywords["permission"], ast.Constant)
    assert keywords["permission"].value == "virtualization.view_virtualmachine"
    assert isinstance(keywords["weight"], ast.Constant)
    assert isinstance(keywords["weight"].value, int)


def test_view_calls_by_vm_resource_endpoint():
    """The VM HA tab must hit /proxmox/cluster/ha/resources/by-vm/{vmid}."""
    source = VM_HA_PATH.read_text(encoding="utf-8")
    assert "/proxmox/cluster/ha/resources/by-vm/" in source


def test_extract_vmid_helper_exists():
    module = _module()
    funcs = {n.name for n in module.body if isinstance(n, ast.FunctionDef)}
    assert "_extract_vmid" in funcs


def test_view_uses_backend_context_helper():
    """The view must resolve the FastAPI backend through the shared helper."""
    source = VM_HA_PATH.read_text(encoding="utf-8")
    assert "get_fastapi_request_context" in source
    assert "translate_request_exception" in source
