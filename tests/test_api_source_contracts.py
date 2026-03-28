from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SERIALIZERS_PATH = REPO_ROOT / "netbox_proxbox" / "api" / "serializers.py"
VIEWS_PATH = REPO_ROOT / "netbox_proxbox" / "api" / "views.py"
FILTERS_PATH = REPO_ROOT / "netbox_proxbox" / "api" / "filters.py"
URLS_PATH = REPO_ROOT / "netbox_proxbox" / "api" / "urls.py"


def _parse_module(path: Path) -> ast.Module:
    return ast.parse(path.read_text(), filename=str(path))


def _classdef(module: ast.Module, name: str) -> ast.ClassDef:
    for node in module.body:
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    raise AssertionError(f"class {name} not found in {module}")


def _assigned_name(node: ast.Assign | ast.AnnAssign) -> str | None:
    if (
        isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
    ):
        return node.targets[0].id
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return node.target.id
    return None


def _meta_fields(class_node: ast.ClassDef) -> tuple[str, ...]:
    meta_node = _classdef(ast.Module(body=class_node.body, type_ignores=[]), "Meta")
    for node in meta_node.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ):
            if node.targets[0].id == "fields":
                return tuple(ast.literal_eval(node.value))
    raise AssertionError(f"Meta.fields not found for {class_node.name}")


def _meta_extra_kwargs(class_node: ast.ClassDef) -> dict:
    meta_node = _classdef(ast.Module(body=class_node.body, type_ignores=[]), "Meta")
    for node in meta_node.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ):
            if node.targets[0].id == "extra_kwargs":
                return ast.literal_eval(node.value)
    return {}


def _class_assignments(class_node: ast.ClassDef) -> set[str]:
    names: set[str] = set()
    for node in class_node.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        name = _assigned_name(node)
        if name:
            names.add(name)
    return names


def _class_methods(class_node: ast.ClassDef) -> set[str]:
    return {node.name for node in class_node.body if isinstance(node, ast.FunctionDef)}


def _meta_brief_fields(class_node: ast.ClassDef) -> tuple[str, ...] | None:
    meta_node = _classdef(ast.Module(body=class_node.body, type_ignores=[]), "Meta")
    for node in meta_node.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ):
            if node.targets[0].id == "brief_fields":
                return tuple(ast.literal_eval(node.value))
    return None


def test_endpoint_serializers_expose_supported_model_fields():
    module = _parse_module(SERIALIZERS_PATH)

    expected = {
        "ProxmoxEndpointSerializer": {
            "name",
            "ip_address",
            "domain",
            "port",
            "mode",
            "version",
            "repoid",
            "username",
            "token_name",
            "verify_ssl",
        },
        "NetBoxEndpointSerializer": {
            "name",
            "ip_address",
            "domain",
            "port",
            "token_version",
            "token",
            "token_key",
            "token_secret",
            "verify_ssl",
        },
        "FastAPIEndpointSerializer": {
            "name",
            "ip_address",
            "domain",
            "port",
            "verify_ssl",
            "token",
            "use_websocket",
            "websocket_domain",
            "websocket_port",
            "server_side_websocket",
        },
        "SyncProcessSerializer": {
            "name",
            "sync_type",
            "status",
            "started_at",
            "completed_at",
            "runtime",
        },
        "VMBackupSerializer": {
            "virtual_machine",
            "storage",
            "subtype",
            "format",
            "creation_time",
            "size",
            "notes",
            "volume_id",
            "vmid",
            "used",
            "encrypted",
            "verification_state",
            "verification_upid",
        },
    }

    for serializer_name, fields in expected.items():
        class_node = _classdef(module, serializer_name)
        meta_fields = set(_meta_fields(class_node))
        missing = fields - meta_fields
        assert not missing, f"{serializer_name} missing fields: {sorted(missing)}"


def test_endpoint_serializers_do_not_override_create_semantics():
    module = _parse_module(SERIALIZERS_PATH)

    for serializer_name in ("NetBoxEndpointSerializer", "FastAPIEndpointSerializer"):
        class_node = _classdef(module, serializer_name)
        assert "create" not in _class_methods(class_node)


def test_netbox_endpoint_serializer_rejects_selected_v2_token_objects():
    contents = SERIALIZERS_PATH.read_text()
    assert "Selected NetBox v2 token cannot be used by this endpoint" in contents


def test_writable_nested_related_fields_are_declared():
    module = _parse_module(SERIALIZERS_PATH)

    expected_assignments = {
        "VMBackupSerializer": {"virtual_machine"},
        "ProxmoxEndpointSerializer": {"ip_address"},
        "NetBoxEndpointSerializer": {"ip_address", "token"},
        "FastAPIEndpointSerializer": {"ip_address"},
    }

    for serializer_name, assignments in expected_assignments.items():
        class_node = _classdef(module, serializer_name)
        present = _class_assignments(class_node)
        missing = assignments - present
        assert not missing, (
            f"{serializer_name} missing class assignments: {sorted(missing)}"
        )


def _call_kwargs_for_assignment(
    class_node: ast.ClassDef, assignment_name: str
) -> dict[str, ast.AST]:
    for node in class_node.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == assignment_name
            and isinstance(node.value, ast.Call)
        ):
            return {
                kw.arg: kw.value for kw in node.value.keywords if kw.arg is not None
            }
    raise AssertionError(f"Assignment {assignment_name} not found in {class_node.name}")


def test_nested_serializers_do_not_pass_nested_keyword_argument():
    module = _parse_module(SERIALIZERS_PATH)
    assignments = [
        ("VMBackupSerializer", "virtual_machine"),
        ("ProxmoxEndpointSerializer", "ip_address"),
        ("NetBoxEndpointSerializer", "ip_address"),
        ("NetBoxEndpointSerializer", "token"),
        ("FastAPIEndpointSerializer", "ip_address"),
    ]

    for serializer_name, assignment_name in assignments:
        class_node = _classdef(module, serializer_name)
        kwargs = _call_kwargs_for_assignment(class_node, assignment_name)
        assert "nested" not in kwargs, (
            f"{serializer_name}.{assignment_name} should not pass nested=... to nested serializers"
        )


def test_proxmox_endpoint_serializer_marks_secrets_write_only():
    module = _parse_module(SERIALIZERS_PATH)
    class_node = _classdef(module, "ProxmoxEndpointSerializer")
    extra_kwargs = _meta_extra_kwargs(class_node)
    assert extra_kwargs["password"]["write_only"] is True
    assert extra_kwargs["token_value"]["write_only"] is True


def test_netbox_endpoint_serializer_marks_token_secret_write_only():
    module = _parse_module(SERIALIZERS_PATH)
    class_node = _classdef(module, "NetBoxEndpointSerializer")
    extra_kwargs = _meta_extra_kwargs(class_node)
    assert extra_kwargs["token_secret"]["write_only"] is True


def test_all_viewsets_use_netbox_model_viewset_and_plugin_filtersets():
    module = _parse_module(VIEWS_PATH)

    expected_viewsets = {
        "VMBackupViewSet": "VMBackupFilterSet",
        "SyncProcessViewSet": "SyncProcessFilterSet",
        "ProxmoxEndpointViewSet": "ProxmoxEndpointFilterSet",
        "NetBoxEndpointViewSet": "NetBoxEndpointFilterSet",
        "FastAPIEndpointViewSet": "FastAPIEndpointFilterSet",
    }

    for viewset_name, filterset_name in expected_viewsets.items():
        class_node = _classdef(module, viewset_name)
        base_names = [
            base.id for base in class_node.bases if isinstance(base, ast.Name)
        ]
        assert "NetBoxModelViewSet" in base_names

        assignments = _class_assignments(class_node)
        assert "queryset" in assignments
        assert "serializer_class" in assignments
        assert "filterset_class" in assignments

        filter_node = next(
            node
            for node in class_node.body
            if isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "filterset_class"
        )
        attr = filter_node.value
        if isinstance(attr, ast.Attribute):
            assert attr.attr == filterset_name
        elif isinstance(attr, ast.Name):
            assert attr.id == filterset_name
        else:
            raise AssertionError(f"Unexpected filterset assignment in {viewset_name}")


def test_api_filters_module_reexports_all_plugin_filtersets():
    module = _parse_module(FILTERS_PATH)
    import_from = next(
        (node for node in module.body if isinstance(node, ast.ImportFrom)), None
    )
    assert import_from is not None
    assert import_from.module == "netbox_proxbox.filtersets"
    exported = {alias.name for alias in import_from.names}
    assert exported == {
        "FastAPIEndpointFilterSet",
        "NetBoxEndpointFilterSet",
        "ProxmoxEndpointFilterSet",
        "SyncProcessFilterSet",
        "VMBackupFilterSet",
    }


def test_nested_writable_serializers_define_brief_fields():
    module = _parse_module(SERIALIZERS_PATH)
    class_node = _classdef(module, "NestedTokenSerializer")
    brief_fields = _meta_brief_fields(class_node)
    assert brief_fields is not None
    assert set(brief_fields) == {"id", "url", "display", "key"}


def test_plugin_api_routes_register_all_plugin_objects():
    module = _parse_module(URLS_PATH)

    endpoint_registers = []
    root_registers = []

    for node in module.body:
        if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
            continue
        call = node.value
        if not isinstance(call.func, ast.Attribute) or call.func.attr != "register":
            continue
        if not isinstance(call.func.value, ast.Name):
            continue

        router_name = call.func.value.id
        if not call.args:
            continue
        route = ast.literal_eval(call.args[0])
        if router_name == "endpoints_router":
            endpoint_registers.append(route)
        elif router_name == "router":
            root_registers.append(route)

    assert set(endpoint_registers) == {"proxmox", "netbox", "fastapi"}
    assert set(root_registers) == {"sync-processes", "backups"}
