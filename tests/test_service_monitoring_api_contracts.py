"""No-DB contracts for service-monitoring API and Services-tab behavior."""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
API_VIEWS_PATH = REPO_ROOT / "netbox_proxbox" / "api" / "views.py"
ENDPOINT_VIEWS_PATH = (
    REPO_ROOT / "netbox_proxbox" / "views" / "endpoints" / "proxmox.py"
)
ENDPOINT_SERIALIZERS_PATH = (
    REPO_ROOT / "netbox_proxbox" / "api" / "serializers" / "endpoints.py"
)
SERVICES_TEMPLATE_PATH = (
    REPO_ROOT
    / "netbox_proxbox"
    / "templates"
    / "netbox_proxbox"
    / "proxmoxendpoint_services.html"
)


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _class_source(path: Path, class_name: str) -> str:
    source = path.read_text(encoding="utf-8")
    module = ast.parse(source, filename=str(path))
    for node in module.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return ast.get_source_segment(source, node) or ""
    raise AssertionError(f"{class_name} not found in {path}")


def _classdef(module: ast.Module, class_name: str) -> ast.ClassDef:
    for node in module.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return node
    raise AssertionError(f"{class_name} not found")


def _field_assignment(class_node: ast.ClassDef, name: str) -> ast.Call:
    for node in class_node.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == name
            and isinstance(node.value, ast.Call)
        ):
            return node.value
    raise AssertionError(f"{name} assignment not found on {class_node.name}")


def _call_keywords(call: ast.Call) -> dict[str, ast.AST]:
    return {kw.arg: kw.value for kw in call.keywords if kw.arg is not None}


def test_refresh_views_require_enabled_and_eligible_before_collection() -> None:
    ui_source = _class_source(ENDPOINT_VIEWS_PATH, "ProxmoxEndpointServicesView")
    api_source = _class_source(API_VIEWS_PATH, "ProxmoxServiceMonitoringRefreshAPIView")

    for source in (ui_source, api_source):
        enabled_index = source.index("not endpoint.service_monitoring_enabled")
        eligible_index = source.index("not endpoint.service_monitoring_eligible")
        collect_index = source.index("collect_systemctl_services")
        assert enabled_index < collect_index
        assert eligible_index < collect_index
        assert "Service monitoring is disabled for this endpoint." in source


def test_services_tab_does_not_offer_refresh_when_monitoring_is_disabled() -> None:
    template = SERVICES_TEMPLATE_PATH.read_text(encoding="utf-8")
    header = template.split('<div class="card-body">', 1)[0]

    assert "{% if object.service_monitoring_enabled %}" in header
    assert "Refresh now" in header
    assert header.index("{% if object.service_monitoring_enabled %}") < header.index(
        "Refresh now"
    )


def test_can_refresh_services_requires_enabled_eligible_and_change_permission() -> None:
    source = _class_source(ENDPOINT_VIEWS_PATH, "ProxmoxEndpointServicesView")
    can_refresh_block = source.split('"can_refresh_services"', 1)[1]

    assert "instance.service_monitoring_enabled" in can_refresh_block
    assert "instance.service_monitoring_eligible" in can_refresh_block
    assert 'get_permission_for_model(ProxmoxEndpoint, "change")' in can_refresh_block


def test_proxmox_endpoint_heartbeat_serializer_fields_are_read_only() -> None:
    module = _parse(ENDPOINT_SERIALIZERS_PATH)
    serializer = _classdef(module, "ProxmoxEndpointSerializer")

    expected = {
        "service_monitoring_last_success_at": "DateTimeField",
        "service_monitoring_last_status": "CharField",
        "service_monitoring_last_error": "CharField",
    }
    for field_name, serializer_field in expected.items():
        call = _field_assignment(serializer, field_name)
        assert isinstance(call.func, ast.Attribute)
        assert call.func.attr == serializer_field
        kwargs = _call_keywords(call)
        assert isinstance(kwargs["read_only"], ast.Constant)
        assert kwargs["read_only"].value is True
