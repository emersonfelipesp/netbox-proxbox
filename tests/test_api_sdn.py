"""Contract tests for the SDN API layer (serializers, viewsets, URL registration)."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text()


# ---------------------------------------------------------------------------
# Serializer contracts
# ---------------------------------------------------------------------------


def test_sdn_serializer_file_exists():
    assert (REPO_ROOT / "netbox_proxbox/api/serializers/sdn.py").exists()


def test_sdn_serializer_exports_all_three_classes():
    content = _read("netbox_proxbox/api/serializers/sdn.py")
    assert "class ProxmoxSdnFabricSerializer" in content
    assert "class ProxmoxSdnRouteMapSerializer" in content
    assert "class ProxmoxSdnPrefixListSerializer" in content


def test_sdn_serializer_uses_netbox_model_serializer():
    content = _read("netbox_proxbox/api/serializers/sdn.py")
    assert "NetBoxModelSerializer" in content


def test_sdn_serializer_includes_endpoint_field():
    content = _read("netbox_proxbox/api/serializers/sdn.py")
    assert "endpoint" in content


def test_sdn_serializer_includes_status_choice_field():
    content = _read("netbox_proxbox/api/serializers/sdn.py")
    assert "ChoiceField" in content or "status" in content


def test_serializers_init_exports_sdn_serializers():
    content = _read("netbox_proxbox/api/serializers/__init__.py")
    assert "ProxmoxSdnFabricSerializer" in content
    assert "ProxmoxSdnRouteMapSerializer" in content
    assert "ProxmoxSdnPrefixListSerializer" in content


# ---------------------------------------------------------------------------
# ViewSet contracts
# ---------------------------------------------------------------------------


def test_sdn_viewsets_defined_in_views():
    content = _read("netbox_proxbox/api/views.py")
    assert "ProxmoxSdnFabricViewSet" in content
    assert "ProxmoxSdnRouteMapViewSet" in content
    assert "ProxmoxSdnPrefixListViewSet" in content


def test_sdn_viewsets_use_netbox_model_viewset():
    content = _read("netbox_proxbox/api/views.py")
    assert "NetBoxModelViewSet" in content


def test_sdn_viewsets_select_related_endpoint():
    content = _read("netbox_proxbox/api/views.py")
    assert 'select_related("endpoint")' in content


# ---------------------------------------------------------------------------
# URL registration
# ---------------------------------------------------------------------------


def test_sdn_routes_registered_in_api_urls():
    content = _read("netbox_proxbox/api/urls.py")
    assert "sdn-fabrics" in content
    assert "sdn-route-maps" in content
    assert "sdn-prefix-lists" in content


def test_sdn_router_basenames_correct():
    content = _read("netbox_proxbox/api/urls.py")
    assert "proxmoxsdnfabric" in content
    assert "proxmoxsdnroutemap" in content
    assert "proxmoxsdnprefixlist" in content
