"""Tests for test_form_and_helper_source_contracts."""

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


def test_endpoint_forms_resolve_loopback_ip_initial_values():
    netbox_contents = _read("netbox_proxbox/forms/netbox.py")
    fastapi_contents = _read("netbox_proxbox/forms/fastapi.py")
    utils_contents = _read("netbox_proxbox/utils.py")

    assert 'self.initial["ip_address"]' in netbox_contents
    assert "resolve_ip_address_initial" in netbox_contents
    assert "IPAddress.objects.filter(pk=candidate).first()" in utils_contents
    assert "IPAddress.objects.filter(address=candidate).first()" in utils_contents

    assert 'self.initial["ip_address"]' in fastapi_contents
    assert "resolve_ip_address_initial" in fastapi_contents
    assert "IPAddress.objects.filter(pk=candidate).first()" in utils_contents
    assert "IPAddress.objects.filter(address=candidate).first()" in utils_contents


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
        "netbox_proxbox/views/home_context.py",
        "netbox_proxbox/views/cards.py",
        "netbox_proxbox/services/service_status.py",
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


def test_netbox_endpoint_form_documents_v2_manual_credential_requirement():
    contents = _read("netbox_proxbox/forms/netbox.py")
    assert "Choose an existing NetBox v1 API token" in contents
    assert "Use token key and token secret fields instead" in contents


def test_netbox_endpoint_form_rejects_unusable_v1_selected_token():
    contents = _read("netbox_proxbox/forms/netbox.py")
    assert (
        "Selected NetBox v1 token does not expose a usable plaintext value" in contents
    )


def test_netbox_endpoint_form_excludes_v2_tokens_from_dropdown():
    """Token dropdown must only show v1 tokens — v2 secrets are not retrievable via FK."""
    contents = _read("netbox_proxbox/forms/netbox.py")
    assert "Token.objects.filter(version=1)" in contents, (
        "NetBoxEndpointForm.token queryset must filter to version=1 so v2 tokens "
        "never appear in the dropdown (their secrets cannot be retrieved via FK). "
        "See GitHub issue #545."
    )


def test_endpoint_forms_require_domain_or_ip_address():
    files = [
        "netbox_proxbox/forms/proxmox.py",
        "netbox_proxbox/forms/netbox.py",
        "netbox_proxbox/forms/fastapi.py",
    ]

    for path in files:
        contents = _read(path)
        assert "Provide either a domain or an IP address." in contents


def test_home_context_builds_prefilled_quick_add_urls():
    contents = _read("netbox_proxbox/views/home_context.py")

    assert "_build_add_url" in contents
    assert "netboxendpoint_add" in contents
    assert "fastapiendpoint_add" in contents
    assert 'domain": "localhost"' in contents
    assert 'ip_address": "127.0.0.1/32"' in contents
    assert 'token_version": NetBoxTokenVersionChoices.V1' in contents


def test_proxmox_import_form_exists_with_csv_fields():
    contents = _read("netbox_proxbox/forms/proxmox.py")
    assert "class ProxmoxEndpointImportForm" in contents
    assert "NetBoxModelImportForm" in contents
    assert "CSVChoiceField" in contents
    # ip_address uses plain CharField + clean_ip_address/get_or_create so imports
    # from other instances auto-create missing IPs (no CSVModelChoiceField needed).
    assert "get_or_create" in contents
    assert "clean_ip_address" in contents


def test_proxmox_endpoint_form_hides_secret_fields_and_preserves_existing_values():
    contents = _read("netbox_proxbox/forms/proxmox.py")
    assert "forms.PasswordInput(" in contents
    assert "render_value=False" in contents
    assert "Leave blank to keep the current value." in contents
    assert 'cleaned_data["password"] = self.instance.password' in contents
    assert 'cleaned_data["token_value"] = self.instance.token_value' in contents


def test_netbox_import_form_auto_creates_ip_address():
    contents = _read("netbox_proxbox/forms/netbox.py")
    assert "class NetBoxEndpointImportForm" in contents
    assert "get_or_create" in contents
    assert "clean_ip_address" in contents


def test_fastapi_import_form_auto_creates_ip_address():
    contents = _read("netbox_proxbox/forms/fastapi.py")
    assert "class FastAPIEndpointImportForm" in contents
    assert "get_or_create" in contents
    assert "clean_ip_address" in contents
    assert "NullableCSVIntegerField" in contents
    assert 'expected="fastapi"' in contents


def test_endpoint_import_forms_detect_wrong_endpoint_exports():
    helper_contents = _read("netbox_proxbox/forms/import_utils.py")
    assert "validate_endpoint_import_headers" in helper_contents
    assert "This import data looks like a {label} export" in helper_contents
    assert '"websocket_port"' in helper_contents
    assert '"token_value"' in helper_contents
    assert '"token_secret"' in helper_contents


def test_fastapi_export_round_trips_nullable_websocket_port_and_https_scheme():
    contents = _read("netbox_proxbox/views/endpoints/fastapi_export.py")
    assert '"use_https"' in contents
    assert "if endpoint.websocket_port is not None" in contents
    assert '"websocket_port": str(endpoint.websocket_port)' not in contents


def test_netbox_fastapi_singleton_import_views_handle_override():
    netbox_contents = _read("netbox_proxbox/views/endpoints/netbox.py")
    fastapi_contents = _read("netbox_proxbox/views/endpoints/fastapi.py")

    for contents, name in [
        (netbox_contents, "netbox.py"),
        (fastapi_contents, "fastapi.py"),
    ]:
        assert "confirm_override" in contents, (
            f"Expected singleton override logic in {name}"
        )
        assert "singleton_import_confirm.html" in contents, (
            f"Expected singleton confirmation template reference in {name}"
        )
        assert "existing.delete()" in contents, (
            f"Expected existing singleton deletion in {name}"
        )


def test_netbox_fastapi_export_views_exist():
    netbox_contents = _read("netbox_proxbox/views/endpoints/netbox.py")
    fastapi_contents = _read("netbox_proxbox/views/endpoints/fastapi.py")

    assert "class NetBoxEndpointExportView" in netbox_contents
    assert "class NetBoxExportQuickAddTokenView" in netbox_contents
    assert "class FastAPIEndpointExportView" in fastapi_contents
    assert "class FastAPIExportQuickAddTokenView" in fastapi_contents


def test_netbox_fastapi_export_helpers_exist():
    netbox_export = _read("netbox_proxbox/views/endpoints/netbox_export.py")
    fastapi_export = _read("netbox_proxbox/views/endpoints/fastapi_export.py")

    assert "_netbox_export_fieldnames" in netbox_export
    assert "_serialize_netbox_endpoint" in netbox_export
    assert "token_key" in netbox_export
    assert "token_secret" in netbox_export

    assert "_fastapi_export_fieldnames" in fastapi_export
    assert "_serialize_fastapi_endpoint" in fastapi_export
    assert '"token"' in fastapi_export
