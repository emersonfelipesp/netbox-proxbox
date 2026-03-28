from __future__ import annotations

import ast
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text()


def test_forms_do_not_depend_on_super_clean_return_value():
    forms_dir = REPO_ROOT / "netbox_proxbox" / "forms"

    for path in forms_dir.glob("*.py"):
        contents = path.read_text()
        assert "= super().clean()" not in contents, (
            f"Unsafe clean() assignment in {path.name}"
        )


def test_netbox_endpoint_form_reads_from_self_cleaned_data():
    contents = _read("netbox_proxbox/forms/netbox.py")
    assert "super().clean()" in contents
    assert "cleaned_data = self.cleaned_data" in contents


def test_runtime_code_does_not_chain_get_fastapi_url_dict_access():
    plugin_dir = REPO_ROOT / "netbox_proxbox"
    chained_get_pattern = re.compile(r"get_fastapi_url\([^\n]*\)\.get\(")

    for path in plugin_dir.rglob("*.py"):
        contents = path.read_text()
        assert not chained_get_pattern.search(contents), (
            f"Chained get_fastapi_url(...).get(...) found in {path}"
        )


def test_runtime_code_validates_fastapi_url_helper_payload_shape():
    runtime_files = [
        "netbox_proxbox/views/__init__.py",
        "netbox_proxbox/views/cards.py",
        "netbox_proxbox/views/keepalive_status.py",
        "netbox_proxbox/views/sync.py",
        "netbox_proxbox/websocket_client.py",
    ]

    for path in runtime_files:
        contents = _read(path)
        assert "or {}" in contents, (
            f"Expected defensive default for helper payload in {path}"
        )
        assert "isinstance(" in contents, (
            f"Expected type check for helper payload in {path}"
        )


def _classdef(module: ast.Module, name: str) -> ast.ClassDef:
    for node in module.body:
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    raise AssertionError(f"class {name} not found")


def _find_assignment_call(class_node: ast.ClassDef, field_name: str) -> ast.Call:
    for node in class_node.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == field_name
            and isinstance(node.value, ast.Call)
        ):
            return node.value
    raise AssertionError(
        f"field assignment {field_name} not found in {class_node.name}"
    )


def _has_kwarg_true(call: ast.Call, keyword: str) -> bool:
    for kw in call.keywords:
        if (
            kw.arg == keyword
            and isinstance(kw.value, ast.Constant)
            and kw.value.value is True
        ):
            return True
    return False


def test_endpoint_forms_enable_ip_address_quick_add():
    forms_to_check = [
        ("netbox_proxbox/forms/netbox.py", "NetBoxEndpointForm"),
        ("netbox_proxbox/forms/proxmox.py", "ProxmoxEndpointForm"),
        ("netbox_proxbox/forms/fastapi.py", "FastAPIEndpointForm"),
    ]

    for relative_path, class_name in forms_to_check:
        module = ast.parse(_read(relative_path), filename=relative_path)
        class_node = _classdef(module, class_name)
        field_call = _find_assignment_call(class_node, "ip_address")
        assert _has_kwarg_true(field_call, "quick_add"), (
            f"{class_name}.ip_address must set quick_add=True"
        )


def test_netbox_endpoint_form_enables_token_quick_add():
    relative_path = "netbox_proxbox/forms/netbox.py"
    module = ast.parse(_read(relative_path), filename=relative_path)
    class_node = _classdef(module, "NetBoxEndpointForm")
    field_call = _find_assignment_call(class_node, "token")
    assert _has_kwarg_true(field_call, "quick_add"), (
        "NetBoxEndpointForm.token must set quick_add=True"
    )
