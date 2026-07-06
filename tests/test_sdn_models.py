"""Contract tests for ProxmoxSdnFabric, ProxmoxSdnRouteMap, and ProxmoxSdnPrefixList models."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text()


# ---------------------------------------------------------------------------
# Model file existence
# ---------------------------------------------------------------------------


def test_sdn_fabric_model_file_exists():
    assert (REPO_ROOT / "netbox_proxbox/models/sdn_fabric.py").exists()


def test_sdn_route_map_model_file_exists():
    assert (REPO_ROOT / "netbox_proxbox/models/sdn_route_map.py").exists()


def test_sdn_prefix_list_model_file_exists():
    assert (REPO_ROOT / "netbox_proxbox/models/sdn_prefix_list.py").exists()


# ---------------------------------------------------------------------------
# Model class and field contracts
# ---------------------------------------------------------------------------


def test_sdn_fabric_model_class_defined():
    content = _read("netbox_proxbox/models/sdn_fabric.py")
    assert "class ProxmoxSdnFabric" in content


def test_sdn_fabric_required_fields():
    content = _read("netbox_proxbox/models/sdn_fabric.py")
    assert "fabric_name" in content
    assert "fabric_type" in content
    assert "cluster_name" in content
    assert "endpoint" in content
    assert "status" in content
    assert "raw_config" in content


def test_sdn_fabric_has_unique_constraint():
    content = _read("netbox_proxbox/models/sdn_fabric.py")
    assert "UniqueConstraint" in content
    assert "fabric_name" in content


def test_sdn_fabric_optional_fields():
    content = _read("netbox_proxbox/models/sdn_fabric.py")
    assert "asn" in content
    assert "vrf_vxlan" in content
    assert "peers" in content
    assert "advertise_subnets" in content


def test_sdn_fabric_inherits_netbox_model():
    content = _read("netbox_proxbox/models/sdn_fabric.py")
    assert "NetBoxModel" in content


def test_sdn_route_map_model_class_defined():
    content = _read("netbox_proxbox/models/sdn_route_map.py")
    assert "class ProxmoxSdnRouteMap" in content


def test_sdn_route_map_required_fields():
    content = _read("netbox_proxbox/models/sdn_route_map.py")
    assert "name" in content
    assert "cluster_name" in content
    assert "endpoint" in content
    assert "action" in content
    assert "status" in content
    assert "raw_config" in content


def test_sdn_route_map_has_unique_constraint():
    content = _read("netbox_proxbox/models/sdn_route_map.py")
    assert "UniqueConstraint" in content


def test_sdn_prefix_list_model_class_defined():
    content = _read("netbox_proxbox/models/sdn_prefix_list.py")
    assert "class ProxmoxSdnPrefixList" in content


def test_sdn_prefix_list_required_fields():
    content = _read("netbox_proxbox/models/sdn_prefix_list.py")
    assert "name" in content
    assert "cidr" in content
    assert "action" in content
    assert "cluster_name" in content
    assert "endpoint" in content
    assert "status" in content
    assert "raw_config" in content


def test_sdn_prefix_list_has_optional_le_ge():
    content = _read("netbox_proxbox/models/sdn_prefix_list.py")
    assert '"le"' in content or "le" in content
    assert '"ge"' in content or "ge" in content


def test_sdn_prefix_list_has_unique_constraint():
    content = _read("netbox_proxbox/models/sdn_prefix_list.py")
    assert "UniqueConstraint" in content


# ---------------------------------------------------------------------------
# Models __init__ exports
# ---------------------------------------------------------------------------


def test_models_init_exports_sdn_models():
    content = _read("netbox_proxbox/models/__init__.py")
    assert "ProxmoxSdnFabric" in content
    assert "ProxmoxSdnRouteMap" in content
    assert "ProxmoxSdnPrefixList" in content


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------


_SQUASH_MIGRATION = (
    "netbox_proxbox/migrations/0039_squashed_0039_0042_pve_9_2_firewall_sdn.py"
)
_SDN_INVENTORY_MIGRATION = (
    "netbox_proxbox/migrations/0055_sdn_sync_controls_and_inventory.py"
)


def test_migration_0041_exists():
    # 0041_pve_9_2 was folded into the consolidated squash migration.
    assert (REPO_ROOT / _SQUASH_MIGRATION).exists()


def test_migration_0041_creates_sdn_tables():
    content = _read(_SQUASH_MIGRATION)
    assert "proxmoxsdnfabric" in content.lower()
    assert "proxmoxsdnroutemap" in content.lower()
    assert "proxmoxsdnprefixlist" in content.lower()


def test_migration_0041_depends_on_0040():
    # The squash covers 0039–0042; its base dependency is 0038_v0_0_16_release.
    content = _read(_SQUASH_MIGRATION)
    assert "0038_v0_0_16_release" in content


def test_sdn_inventory_migration_exists_after_endpoint_ssh_source_migration():
    content = _read(_SDN_INVENTORY_MIGRATION)
    assert "0054_proxmoxendpoint_ssh_credential_source" in content
    assert "sync_mode_sdn" in content
    assert "proxmoxsdncontroller" in content.lower()
    assert "proxmoxsdnbinding" in content.lower()


def test_sdn_bgp_sync_mode_migration_exists_after_sdn_inventory_migration():
    content = _read("netbox_proxbox/migrations/0057_sdn_bgp_sync_mode.py")
    assert "0056_proxmoxendpoint_access_methods" in content
    assert "sync_mode_sdn_bgp" in content


# ---------------------------------------------------------------------------
# Choices
# ---------------------------------------------------------------------------


def test_sdn_fabric_type_choices_defined():
    content = _read("netbox_proxbox/choices.py")
    assert "SdnFabricTypeChoices" in content
    assert "wireguard" in content.lower()
    assert "bgp" in content.lower()
    assert "vxlan" in content.lower()
    assert "ospf" in content.lower()


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------


def test_navigation_has_sdn_group():
    content = _read("netbox_proxbox/navigation.py")
    assert "sdn_fabrics_item" in content
    assert "sdn_route_maps_item" in content
    assert "sdn_prefix_lists_item" in content
    assert '"SDN"' in content or "'SDN'" in content


def test_navigation_sdn_items_point_to_correct_links():
    content = _read("netbox_proxbox/navigation.py")
    assert "proxmoxsdnfabric_list" in content
    assert "proxmoxsdnroutemap_list" in content
    assert "proxmoxsdnprefixlist_list" in content


# ---------------------------------------------------------------------------
# URL patterns
# ---------------------------------------------------------------------------


def test_urls_register_sdn_model_urls():
    content = _read("netbox_proxbox/urls.py")
    assert "proxmoxsdnfabric" in content.lower()
    assert "proxmoxsdnroutemap" in content.lower()
    assert "proxmoxsdnprefixlist" in content.lower()


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------


def test_sdn_views_file_exists():
    assert (REPO_ROOT / "netbox_proxbox/views/sdn.py").exists()


def test_sdn_views_define_expected_list_views():
    content = _read("netbox_proxbox/views/sdn.py")
    assert "ProxmoxSdnFabricListView" in content
    assert "ProxmoxSdnRouteMapListView" in content
    assert "ProxmoxSdnPrefixListListView" in content


def test_sdn_views_use_register_model_view():
    content = _read("netbox_proxbox/views/sdn.py")
    assert "register_model_view" in content


def test_views_init_exports_sdn_views():
    content = _read("netbox_proxbox/views/__init__.py")
    assert "sdn" in content.lower()


# ---------------------------------------------------------------------------
# Filtersets
# ---------------------------------------------------------------------------


def test_filtersets_define_sdn_filtersets():
    content = _read("netbox_proxbox/filtersets.py")
    assert "ProxmoxSdnFabricFilterSet" in content
    assert "ProxmoxSdnRouteMapFilterSet" in content
    assert "ProxmoxSdnPrefixListFilterSet" in content


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------


def test_sdn_tables_file_exists():
    assert (REPO_ROOT / "netbox_proxbox/tables/sdn.py").exists()


def test_sdn_tables_define_expected_classes():
    content = _read("netbox_proxbox/tables/sdn.py")
    assert "ProxmoxSdnFabricTable" in content
    assert "ProxmoxSdnRouteMapTable" in content
    assert "ProxmoxSdnPrefixListTable" in content


def test_tables_init_exports_sdn_tables():
    content = _read("netbox_proxbox/tables/__init__.py")
    assert "ProxmoxSdnFabricTable" in content
    assert "ProxmoxSdnRouteMapTable" in content
    assert "ProxmoxSdnPrefixListTable" in content


# ---------------------------------------------------------------------------
# Forms
# ---------------------------------------------------------------------------


def test_sdn_forms_file_exists():
    assert (REPO_ROOT / "netbox_proxbox/forms/sdn.py").exists()


def test_sdn_forms_define_expected_classes():
    content = _read("netbox_proxbox/forms/sdn.py")
    assert "ProxmoxSdnFabricForm" in content
    assert "ProxmoxSdnRouteMapForm" in content
    assert "ProxmoxSdnPrefixListForm" in content


def test_forms_init_exports_sdn_forms():
    content = _read("netbox_proxbox/forms/__init__.py")
    assert "ProxmoxSdnFabricForm" in content
    assert "ProxmoxSdnRouteMapForm" in content
    assert "ProxmoxSdnPrefixListForm" in content


# ---------------------------------------------------------------------------
# Sync service
# ---------------------------------------------------------------------------


def test_sync_sdn_service_file_exists():
    assert (REPO_ROOT / "netbox_proxbox/services/sync_sdn.py").exists()


def test_sync_sdn_service_defines_sync_function():
    content = _read("netbox_proxbox/services/sync_sdn.py")
    assert "def sync_sdn" in content


def test_sync_sdn_service_fetches_fabrics_route_maps_prefix_lists():
    content = _read("netbox_proxbox/services/sync_sdn.py")
    assert "/proxmox/sdn/fabrics" in content
    assert "/proxmox/sdn/route-maps" in content
    assert "/proxmox/sdn/prefix-lists" in content


def test_sync_sdn_service_has_result_dataclass():
    content = _read("netbox_proxbox/services/sync_sdn.py")
    assert "SdnSyncResult" in content
    assert "fabrics_created" in content
    assert "route_maps_created" in content
    assert "prefix_lists_created" in content
    assert "per_endpoint" in content
    assert "runtime_seconds" in content
