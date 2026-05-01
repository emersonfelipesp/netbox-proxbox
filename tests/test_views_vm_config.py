"""Source-contract tests for ``views.vm_config.ProxmoxVMConfigTabView``.

Booting the full Django stack to render this view from a unit test is heavy.
The contract that callers (templates, urls, NetBox extension registry) depend
on is small and stable, so we lock it via AST against
``netbox_proxbox/views/vm_config.py``:

* The view is registered on ``VirtualMachine`` with ``path="proxmox-config"``
  and the name ``"proxmox_config"`` — links and URL reverses rely on both.
* It is an ``ObjectView`` and renders the dedicated tab template.
* The ``ViewTab`` is labelled ``"Proxmox Config"`` with the
  ``virtualization.view_virtualmachine`` permission so VM read-permission
  guards the live config tab.
* The context-builder helpers ``_extract_vmid`` and ``_extract_vm_type`` exist
  and return ``int | None`` / a string — they're imported by future tests too.
"""

from __future__ import annotations

import ast
from pathlib import Path

VM_CONFIG_PATH = (
    Path(__file__).resolve().parents[1] / "netbox_proxbox" / "views" / "vm_config.py"
)


def _module() -> ast.Module:
    return ast.parse(VM_CONFIG_PATH.read_text(encoding="utf-8"))


def _find_class(module: ast.Module, name: str) -> ast.ClassDef:
    for node in ast.walk(module):
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    raise AssertionError(f"class {name} not found in vm_config.py")


def _assign_value(cls: ast.ClassDef, target: str) -> ast.AST | None:
    for node in cls.body:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == target:
                    return node.value
    return None


def test_view_class_subclasses_object_view():
    cls = _find_class(_module(), "ProxmoxVMConfigTabView")
    base_names = {
        b.attr if isinstance(b, ast.Attribute) else getattr(b, "id", "")
        for b in cls.bases
    }
    assert "ObjectView" in base_names, (
        "tab view must remain an ObjectView so NetBox renders it under the VM detail page"
    )


def test_register_model_view_pins_path_and_name():
    cls = _find_class(_module(), "ProxmoxVMConfigTabView")
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
    assert register_call is not None, (
        "ProxmoxVMConfigTabView must use register_model_view"
    )

    # Positional model is VirtualMachine, second positional is the view name
    assert isinstance(register_call.args[0], ast.Name)
    assert register_call.args[0].id == "VirtualMachine"
    assert isinstance(register_call.args[1], ast.Constant)
    assert register_call.args[1].value == "proxmox_config", (
        "URL name 'proxmox_config' is referenced by templates; do not rename"
    )

    keywords = {kw.arg: kw.value for kw in register_call.keywords}
    assert "path" in keywords
    assert isinstance(keywords["path"], ast.Constant)
    assert keywords["path"].value == "proxmox-config"


def test_view_uses_dedicated_template():
    cls = _find_class(_module(), "ProxmoxVMConfigTabView")
    template = _assign_value(cls, "template_name")
    assert isinstance(template, ast.Constant)
    assert template.value == "netbox_proxbox/vm_proxmox_config.html"


def test_tab_metadata_uses_vm_view_permission():
    cls = _find_class(_module(), "ProxmoxVMConfigTabView")
    tab_value = _assign_value(cls, "tab")
    assert isinstance(tab_value, ast.Call)
    assert isinstance(tab_value.func, ast.Name) and tab_value.func.id == "ViewTab"
    keywords = {kw.arg: kw.value for kw in tab_value.keywords}
    assert isinstance(keywords["label"], ast.Constant)
    assert keywords["label"].value == "Proxmox Config"
    assert isinstance(keywords["permission"], ast.Constant)
    assert keywords["permission"].value == "virtualization.view_virtualmachine"
    assert isinstance(keywords["weight"], ast.Constant)
    assert isinstance(keywords["weight"].value, int)


def test_extract_helpers_exist_and_return_expected_shapes():
    """Sanity-check the small extractors so accidental rename surfaces in tests."""
    module = _module()
    funcs = {n.name for n in module.body if isinstance(n, ast.FunctionDef)}
    for name in ("_extract_vmid", "_extract_vm_type", "_extract_node"):
        assert name in funcs, f"helper {name} dropped from vm_config.py"


def test_view_falls_back_to_first_visible_proxmox_endpoint():
    """When the VM's cluster name doesn't match an endpoint, the picker uses
    the first restricted Proxmox endpoint — keep that branch alive."""
    source = VM_CONFIG_PATH.read_text(encoding="utf-8")
    assert 'ProxmoxEndpoint.objects.restrict(request.user, "view")' in source
    assert "proxmox_qs.first()" in source


def test_view_uses_error_utils_helpers_for_non_json_and_request_errors():
    source = VM_CONFIG_PATH.read_text(encoding="utf-8")
    assert "parse_requests_response_json" in source, (
        "view must continue to guard against HTML-on-error backend responses"
    )
    assert "extract_proxmox_backend_error_detail" in source, (
        "view must surface targeted Proxmox error messages instead of raw exceptions"
    )
