"""Tests for test_api_source_contracts."""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_overwrite_fields() -> tuple[str, ...]:
    """Load `OVERWRITE_FIELDS` from `constants.py` without importing the package.

    The plugin's `__init__.py` requires a live NetBox install, which is not
    available during unit-test collection — bypass it by loading the
    constants module directly from disk.
    """
    spec = importlib.util.spec_from_file_location(
        "_netbox_proxbox_constants",
        REPO_ROOT / "netbox_proxbox" / "constants.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return tuple(module.OVERWRITE_FIELDS)


OVERWRITE_FIELDS = _load_overwrite_fields()

_STARRED_CONSTANTS: dict[str, tuple[str, ...]] = {
    "OVERWRITE_FIELDS": OVERWRITE_FIELDS,
}
SERIALIZERS_PACKAGE = REPO_ROOT / "netbox_proxbox" / "api" / "serializers"
VIEWS_PATH = REPO_ROOT / "netbox_proxbox" / "api" / "views.py"
FILTERS_PATH = REPO_ROOT / "netbox_proxbox" / "api" / "filters.py"
URLS_PATH = REPO_ROOT / "netbox_proxbox" / "api" / "urls.py"
PROXMOX_ENDPOINT_VIEWS_PATH = (
    REPO_ROOT / "netbox_proxbox" / "views" / "endpoints" / "proxmox.py"
)


def _parse_module(path: Path) -> ast.Module:
    return ast.parse(path.read_text(), filename=str(path))


def _serializer_module_paths() -> list[Path]:
    return sorted(
        p for p in SERIALIZERS_PACKAGE.glob("*.py") if p.name != "__init__.py"
    )


def _parse_serializers_package() -> ast.Module:
    """Merge serializer submodules into one AST for class lookups."""
    body: list[ast.stmt] = []
    for path in _serializer_module_paths():
        body.extend(_parse_module(path).body)
    return ast.Module(body=body, type_ignores=[])


def _serializers_package_source_text() -> str:
    return "\n".join(p.read_text() for p in _serializer_module_paths())


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


def _resolve_field_sequence(node: ast.AST) -> tuple[str, ...]:
    """Evaluate a fields tuple/list, resolving `*OVERWRITE_FIELDS` star-unpacking."""
    if not isinstance(node, (ast.Tuple, ast.List)):
        return tuple(ast.literal_eval(node))
    resolved: list[str] = []
    for elt in node.elts:
        if isinstance(elt, ast.Starred) and isinstance(elt.value, ast.Name):
            name = elt.value.id
            if name not in _STARRED_CONSTANTS:
                raise AssertionError(
                    f"Unknown star-unpacked constant in Meta.fields: *{name}"
                )
            resolved.extend(_STARRED_CONSTANTS[name])
        else:
            resolved.append(ast.literal_eval(elt))
    return tuple(resolved)


def _meta_fields(class_node: ast.ClassDef) -> tuple[str, ...]:
    meta_node = _classdef(ast.Module(body=class_node.body, type_ignores=[]), "Meta")
    for node in meta_node.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ):
            if node.targets[0].id == "fields":
                return _resolve_field_sequence(node.value)
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
    module = _parse_serializers_package()

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
            "site",
            "tenant",
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
        "VMSnapshotSerializer": {
            "id",
            "url",
            "display",
            "proxmox_storage",
            "virtual_machine",
            "name",
            "description",
            "vmid",
            "node",
            "snaptime",
            "parent",
            "subtype",
            "status",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        },
        "VMTaskHistorySerializer": {
            "id",
            "url",
            "display",
            "virtual_machine",
            "vm_type",
            "upid",
            "node",
            "pid",
            "pstart",
            "task_id",
            "task_type",
            "username",
            "start_time",
            "end_time",
            "description",
            "status",
            "task_state",
            "exitstatus",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        },
        "VMBackupSerializer": {
            "proxmox_storage",
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


def test_cluster_serializer_uses_supported_netbox_virtualization_import():
    contents = (
        REPO_ROOT / "netbox_proxbox" / "api" / "serializers" / "cluster.py"
    ).read_text()

    assert (
        "virtualization.api.serializers_.clusters import ClusterSerializer" in contents
    )
    assert "NestedClusterSerializer" not in contents
    assert (
        "netbox_cluster = ClusterSerializer(nested=True, required=False, allow_null=True)"
        in contents
    )


def test_endpoint_serializers_do_not_override_create_semantics():
    module = _parse_serializers_package()

    for serializer_name in ("NetBoxEndpointSerializer", "FastAPIEndpointSerializer"):
        class_node = _classdef(module, serializer_name)
        assert "create" not in _class_methods(class_node)


def test_overwrite_fields_exposed_in_endpoint_and_settings_serializers():
    """Every flag in `OVERWRITE_FIELDS` must round-trip through the REST API.

    Regression for issue #343: previously the serializers hardcoded only the
    original 5 flag names and silently dropped the 16 added in the expansion.
    """
    module = _parse_serializers_package()

    for serializer_name in (
        "ProxmoxEndpointSerializer",
        "ProxboxPluginSettingsSerializer",
    ):
        class_node = _classdef(module, serializer_name)
        meta_fields = set(_meta_fields(class_node))
        missing = set(OVERWRITE_FIELDS) - meta_fields
        assert not missing, (
            f"{serializer_name} is missing overwrite fields: {sorted(missing)}"
        )


def test_task_history_route_and_viewset_are_registered():
    views_contents = VIEWS_PATH.read_text()
    urls_contents = URLS_PATH.read_text()
    serializers_contents = _serializers_package_source_text()

    assert "VMTaskHistoryViewSet" in views_contents
    assert (
        'router.register("task-history", views.VMTaskHistoryViewSet)' in urls_contents
    )
    # Upsert logic lives in the serializer's create() so it covers both single and bulk POSTs.
    assert "VMTaskHistory.objects.filter(upid=upid).first()" in serializers_contents


def test_netbox_endpoint_serializer_rejects_selected_v2_token_objects():
    contents = _serializers_package_source_text()
    assert "Selected NetBox v2 token cannot be used by this endpoint" in contents


def test_netbox_endpoint_serializer_rejects_unusable_v1_selected_token():
    contents = _serializers_package_source_text()
    assert "Selected NetBox v1 token does not expose a usable plaintext" in contents


def test_endpoint_serializers_require_domain_or_ip_address():
    contents = _serializers_package_source_text()
    assert contents.count("Provide either a domain or an IP address.") >= 3


def test_keepalive_builds_v2_token_and_compacts_payload():
    keepalive_path = REPO_ROOT / "netbox_proxbox" / "services" / "service_status.py"
    contents = keepalive_path.read_text()
    assert "_effective_netbox_backend_credentials" in contents
    assert "_compact_payload" in contents
    assert '"token_key"' in contents


def test_writable_nested_related_fields_are_declared():
    module = _parse_serializers_package()

    expected_assignments = {
        "VMBackupSerializer": {"proxmox_storage", "virtual_machine"},
        "VMSnapshotSerializer": {"proxmox_storage", "virtual_machine"},
        "ProxmoxEndpointSerializer": {"ip_address", "site", "tenant"},
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
    module = _parse_serializers_package()
    assignments = [
        ("VMBackupSerializer", "virtual_machine"),
        ("VMBackupSerializer", "proxmox_storage"),
        ("VMSnapshotSerializer", "virtual_machine"),
        ("VMSnapshotSerializer", "proxmox_storage"),
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
    module = _parse_serializers_package()
    class_node = _classdef(module, "ProxmoxEndpointSerializer")
    extra_kwargs = _meta_extra_kwargs(class_node)
    assert extra_kwargs["password"]["write_only"] is True
    assert extra_kwargs["token_value"]["write_only"] is True


def test_netbox_endpoint_serializer_marks_token_secret_write_only():
    module = _parse_serializers_package()
    class_node = _classdef(module, "NetBoxEndpointSerializer")
    extra_kwargs = _meta_extra_kwargs(class_node)
    assert extra_kwargs["token_secret"]["write_only"] is True


def test_all_viewsets_use_netbox_model_viewset_and_plugin_filtersets():
    module = _parse_module(VIEWS_PATH)

    expected_viewsets = {
        "VMBackupViewSet": "VMBackupFilterSet",
        "VMSnapshotViewSet": "VMSnapshotFilterSet",
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
        "VMBackupFilterSet",
        "VMSnapshotFilterSet",
    }


def test_nested_writable_serializers_define_brief_fields():
    module = _parse_serializers_package()
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
    assert set(root_registers) == {
        "backup-routines",
        "proxmox-clusters",
        "proxmox-nodes",
        "replications",
        "settings",
        "storage",
        "backups",
        "snapshots",
        "task-history",
    }


def test_proxmox_endpoint_views_register_bulk_import_and_csv_export():
    contents = PROXMOX_ENDPOINT_VIEWS_PATH.read_text()
    assert (
        '@register_model_view(ProxmoxEndpoint, "bulk_import", path="import", detail=False)'
        in contents
    )
    assert "class ProxmoxEndpointBulkImportView" in contents
    assert "model_form = ProxmoxEndpointImportForm" in contents
    assert (
        '@register_model_view(ProxmoxEndpoint, "export", path="export", detail=False)'
        in contents
    )
    assert "class ProxmoxEndpointExportView" in contents


def test_proxmox_endpoint_export_requires_token_for_sensitive_payloads():
    contents = PROXMOX_ENDPOINT_VIEWS_PATH.read_text()
    assert "include_sensitive" in contents
    assert "TokenAuthentication" in contents
    assert "A valid NetBox token is required to export secrets." in contents
    assert 'allowed_formats = {"csv", "json", "yaml"}' in contents


# ---------------------------------------------------------------------------
# Non-model API views (added alongside the model viewsets)
# ---------------------------------------------------------------------------

_NON_MODEL_VIEWS = [
    "HomeAPIView",
    "DashboardAPIView",
    "NodesAPIView",
    "VirtualMachinesAPIView",
    "LXCContainersAPIView",
    "InterfacesAPIView",
    "IPAddressesAPIView",
    "VirtualDisksAPIView",
    "ScheduleSyncAPIView",
    "BackendLogsAPIView",
]

_DASHBOARD_PERMISSION_VIEWS = {"HomeAPIView", "DashboardAPIView"}
_RESOURCE_PERMISSION_VIEWS = {
    "NodesAPIView",
    "VirtualMachinesAPIView",
    "LXCContainersAPIView",
    "InterfacesAPIView",
    "IPAddressesAPIView",
    "VirtualDisksAPIView",
    "ScheduleSyncAPIView",
    "BackendLogsAPIView",
}


def _find_permission_classes_value(class_node: ast.ClassDef) -> list[str] | None:
    """Return the string names in permission_classes = [...] or None if absent."""
    for node in class_node.body:
        if not isinstance(node, ast.Assign):
            continue
        if (
            len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "permission_classes"
            and isinstance(node.value, ast.List)
        ):
            names = []
            for elt in node.value.elts:
                if isinstance(elt, ast.Name):
                    names.append(elt.id)
                elif isinstance(elt, ast.Attribute):
                    names.append(elt.attr)
            return names
    return None


def test_non_model_api_views_exist_and_extend_api_view():
    """Every non-model API view must exist and subclass APIView (directly or via a base)."""
    module = _parse_module(VIEWS_PATH)

    def _bases(class_node: ast.ClassDef) -> list[str]:
        return [b.id if isinstance(b, ast.Name) else b.attr for b in class_node.bases]

    def _inherits_api_view(class_node: ast.ClassDef) -> bool:
        direct = _bases(class_node)
        if "APIView" in direct:
            return True
        # Check one level up for intermediate base classes defined in the same module.
        for base_name in direct:
            try:
                base_node = _classdef(module, base_name)
                if "APIView" in _bases(base_node):
                    return True
            except (KeyError, AssertionError):
                pass
        return False

    for view_name in _NON_MODEL_VIEWS:
        class_node = _classdef(module, view_name)
        assert _inherits_api_view(class_node), (
            f"{view_name} must subclass APIView (directly or via a base), "
            f"got bases: {_bases(class_node)}"
        )


def test_non_model_api_views_define_get_method():
    """Every non-model view must expose a get() handler (directly or via a base)."""
    module = _parse_module(VIEWS_PATH)

    def _has_method(class_node: ast.ClassDef, method: str) -> bool:
        if method in _class_methods(class_node):
            return True
        # Check one level up for methods defined on an intermediate base in the same module.
        for base_name in [
            b.id if isinstance(b, ast.Name) else b.attr for b in class_node.bases
        ]:
            try:
                base_node = _classdef(module, base_name)
                if method in _class_methods(base_node):
                    return True
            except (KeyError, AssertionError):
                pass
        return False

    for view_name in _NON_MODEL_VIEWS:
        class_node = _classdef(module, view_name)
        assert _has_method(class_node, "get"), f"{view_name} is missing a get() method"


def test_schedule_sync_api_view_defines_post_and_permission_check():
    """ScheduleSyncAPIView must have post() and the _check_enqueue_permission helper."""
    module = _parse_module(VIEWS_PATH)
    class_node = _classdef(module, "ScheduleSyncAPIView")
    methods = _class_methods(class_node)
    assert "post" in methods, "ScheduleSyncAPIView must define post()"
    assert "_check_enqueue_permission" in methods, (
        "ScheduleSyncAPIView must define _check_enqueue_permission()"
    )


def test_dashboard_views_use_proxbox_dashboard_permission():
    """HomeAPIView and DashboardAPIView must use _ProxboxDashboardPermission."""
    module = _parse_module(VIEWS_PATH)
    for view_name in _DASHBOARD_PERMISSION_VIEWS:
        class_node = _classdef(module, view_name)
        perms = _find_permission_classes_value(class_node)
        assert perms is not None, f"{view_name} must declare permission_classes"
        assert "_ProxboxDashboardPermission" in perms, (
            f"{view_name} permission_classes must include _ProxboxDashboardPermission, got {perms}"
        )


def test_resource_views_use_is_authenticated_or_login_not_required():
    """Resource/log/schedule views must use IsAuthenticatedOrLoginNotRequired."""
    module = _parse_module(VIEWS_PATH)

    def _find_perms(class_node: ast.ClassDef) -> list[str] | None:
        perms = _find_permission_classes_value(class_node)
        if perms is not None:
            return perms
        # Check one level up for permission_classes defined on an intermediate base.
        for base_name in [
            b.id if isinstance(b, ast.Name) else b.attr for b in class_node.bases
        ]:
            try:
                base_node = _classdef(module, base_name)
                perms = _find_permission_classes_value(base_node)
                if perms is not None:
                    return perms
            except (KeyError, AssertionError):
                pass
        return None

    for view_name in _RESOURCE_PERMISSION_VIEWS:
        class_node = _classdef(module, view_name)
        perms = _find_perms(class_node)
        assert perms is not None, f"{view_name} must declare permission_classes"
        assert "IsAuthenticatedOrLoginNotRequired" in perms, (
            f"{view_name} permission_classes must include IsAuthenticatedOrLoginNotRequired, got {perms}"
        )


def test_proxbox_dashboard_permission_class_exists_in_views():
    """_ProxboxDashboardPermission must exist as a class in views.py."""
    module = _parse_module(VIEWS_PATH)
    _classdef(module, "_ProxboxDashboardPermission")  # raises if missing


def test_non_model_views_registered_in_urlpatterns():
    """All non-model view paths must appear in the api/urls.py urlpatterns."""
    contents = URLS_PATH.read_text()
    expected_paths = [
        '"home/"',
        '"dashboard/"',
        '"resources/clusters/"',
        '"resources/nodes/"',
        '"resources/virtual-machines/"',
        '"resources/lxc-containers/"',
        '"resources/interfaces/"',
        '"resources/ip-addresses/"',
        '"resources/virtual-disks/"',
        '"sync/schedule/"',
        '"logs/"',
    ]
    for path_str in expected_paths:
        assert path_str in contents, f"URL path {path_str} not found in api/urls.py"


def test_api_root_view_exposes_all_non_model_url_keys():
    """ProxBoxRootView.get() must set home, dashboard, resources, schedule_sync, and logs."""
    contents = VIEWS_PATH.read_text()
    expected_keys = [
        'response.data["home"]',
        'response.data["dashboard"]',
        'response.data["resources"]',
        'response.data["schedule_sync"]',
        'response.data["logs"]',
    ]
    for key_expr in expected_keys:
        assert key_expr in contents, f"ProxBoxRootView.get() is missing: {key_expr}"


def test_resource_view_serializers_exist_in_package():
    """Lightweight non-model response serializers must exist in the serializers package."""
    module = _parse_serializers_package()
    expected = [
        "DeviceResourceSerializer",
        "VirtualMachineResourceSerializer",
        "InterfaceResourceSerializer",
        "IPAddressResourceSerializer",
        "VirtualDiskResourceSerializer",
        "ScheduledJobSerializer",
        "ScheduleSyncRequestSerializer",
    ]
    for serializer_name in expected:
        _classdef(module, serializer_name)  # raises AssertionError if not found


def test_resource_serializers_have_expected_fields():
    """Spot-check key fields on each non-model response serializer."""
    module = _parse_serializers_package()

    expected_assignments = {
        "DeviceResourceSerializer": {
            "id",
            "name",
            "url",
            "device_type",
            "manufacturer",
            "interfaces",
        },
        "VirtualMachineResourceSerializer": {
            "id",
            "name",
            "url",
            "cluster",
            "interfaces",
        },
        "InterfaceResourceSerializer": {
            "id",
            "name",
            "enabled",
            "parent_type",
            "parent_name",
            "ip_addresses",
        },
        "IPAddressResourceSerializer": {
            "id",
            "address",
            "assigned_object_type",
        },
        "VirtualDiskResourceSerializer": {
            "id",
            "name",
            "size",
            "virtual_machine",
        },
        "ScheduledJobSerializer": {
            "id",
            "name",
            "sync_types",
            "schedule",
            "interval",
            "status",
        },
        "ScheduleSyncRequestSerializer": {
            "sync_types",
            "job_name",
            "schedule_at",
            "interval_value",
            "interval_unit",
        },
    }

    for serializer_name, required_fields in expected_assignments.items():
        class_node = _classdef(module, serializer_name)
        present = _class_assignments(class_node)
        missing = required_fields - present
        assert not missing, (
            f"{serializer_name} missing field assignments: {sorted(missing)}"
        )


def test_schedule_sync_request_serializer_requires_sync_types():
    """ScheduleSyncRequestSerializer.sync_types must have min_length=1."""
    contents = (SERIALIZERS_PACKAGE / "resource_views.py").read_text()
    # min_length=1 enforces at least one sync type slug
    assert "min_length=1" in contents
