"""Contract tests for ProxmoxDatacenterCpuModel model and its API layer."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text()


# ---------------------------------------------------------------------------
# Model file existence and class contract
# ---------------------------------------------------------------------------


def test_datacenter_cpu_model_file_exists():
    assert (REPO_ROOT / "netbox_proxbox/models/datacenter_cpu_model.py").exists()


def test_datacenter_cpu_model_class_defined():
    content = _read("netbox_proxbox/models/datacenter_cpu_model.py")
    assert "class ProxmoxDatacenterCpuModel" in content


def test_datacenter_cpu_model_inherits_netbox_model():
    content = _read("netbox_proxbox/models/datacenter_cpu_model.py")
    assert "NetBoxModel" in content


def test_datacenter_cpu_model_required_fields():
    content = _read("netbox_proxbox/models/datacenter_cpu_model.py")
    assert "cputype" in content
    assert "cluster_name" in content
    assert "endpoint" in content
    assert "status" in content
    assert "raw_config" in content


def test_datacenter_cpu_model_optional_fields():
    content = _read("netbox_proxbox/models/datacenter_cpu_model.py")
    assert "base_cputype" in content
    assert "flags" in content
    assert "vendor_id" in content
    assert "level" in content
    assert "description" in content


def test_datacenter_cpu_model_has_unique_constraint():
    content = _read("netbox_proxbox/models/datacenter_cpu_model.py")
    assert "UniqueConstraint" in content
    assert "cputype" in content


# ---------------------------------------------------------------------------
# Models __init__ exports
# ---------------------------------------------------------------------------


def test_models_init_exports_cpu_model():
    content = _read("netbox_proxbox/models/__init__.py")
    assert "ProxmoxDatacenterCpuModel" in content


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------


_SQUASH_MIGRATION = (
    "netbox_proxbox/migrations/0039_squashed_0039_0042_pve_9_2_firewall_sdn.py"
)


def test_migration_0041_creates_cpu_model_table():
    # 0041_pve_9_2 was folded into the consolidated squash migration.
    content = _read(_SQUASH_MIGRATION)
    assert "proxmoxdatacentercpumodel" in content.lower()


def test_migration_0041_adds_node_location_field():
    # 0041_pve_9_2 was folded into the consolidated squash migration.
    content = _read(_SQUASH_MIGRATION)
    assert "location" in content
    assert "proxmoxnode" in content.lower()


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------


def test_navigation_has_datacenter_cpu_models_item():
    content = _read("netbox_proxbox/navigation.py")
    assert "datacenter_cpu_models_item" in content
    assert "proxmoxdatacentercpumodel_list" in content


def test_navigation_cpu_models_in_infrastructure_group():
    content = _read("netbox_proxbox/navigation.py")
    assert "Infrastructure" in content
    assert "datacenter_cpu_models_item" in content


# ---------------------------------------------------------------------------
# URL patterns
# ---------------------------------------------------------------------------


def test_urls_register_cpu_model_urls():
    content = _read("netbox_proxbox/urls.py")
    assert "proxmoxdatacentercpumodel" in content.lower()


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------


def test_datacenter_views_file_exists():
    assert (REPO_ROOT / "netbox_proxbox/views/datacenter.py").exists()


def test_datacenter_views_define_list_view():
    content = _read("netbox_proxbox/views/datacenter.py")
    assert "ProxmoxDatacenterCpuModelListView" in content


def test_datacenter_views_use_register_model_view():
    content = _read("netbox_proxbox/views/datacenter.py")
    assert "register_model_view" in content


# ---------------------------------------------------------------------------
# Filterset
# ---------------------------------------------------------------------------


def test_filtersets_define_cpu_model_filterset():
    content = _read("netbox_proxbox/filtersets.py")
    assert "ProxmoxDatacenterCpuModelFilterSet" in content


# ---------------------------------------------------------------------------
# Table
# ---------------------------------------------------------------------------


def test_datacenter_tables_file_exists():
    assert (REPO_ROOT / "netbox_proxbox/tables/datacenter.py").exists()


def test_datacenter_tables_define_expected_class():
    content = _read("netbox_proxbox/tables/datacenter.py")
    assert "ProxmoxDatacenterCpuModelTable" in content


def test_tables_init_exports_cpu_model_table():
    content = _read("netbox_proxbox/tables/__init__.py")
    assert "ProxmoxDatacenterCpuModelTable" in content


# ---------------------------------------------------------------------------
# Forms
# ---------------------------------------------------------------------------


def test_datacenter_forms_file_exists():
    assert (REPO_ROOT / "netbox_proxbox/forms/datacenter.py").exists()


def test_datacenter_forms_define_expected_classes():
    content = _read("netbox_proxbox/forms/datacenter.py")
    assert "ProxmoxDatacenterCpuModelForm" in content


def test_forms_init_exports_datacenter_forms():
    content = _read("netbox_proxbox/forms/__init__.py")
    assert "ProxmoxDatacenterCpuModelForm" in content


# ---------------------------------------------------------------------------
# API layer
# ---------------------------------------------------------------------------


def test_datacenter_serializer_file_exists():
    assert (REPO_ROOT / "netbox_proxbox/api/serializers/datacenter.py").exists()


def test_datacenter_serializer_class_defined():
    content = _read("netbox_proxbox/api/serializers/datacenter.py")
    assert "class ProxmoxDatacenterCpuModelSerializer" in content


def test_serializers_init_exports_datacenter_serializer():
    content = _read("netbox_proxbox/api/serializers/__init__.py")
    assert "ProxmoxDatacenterCpuModelSerializer" in content


def test_datacenter_viewset_defined_in_views():
    content = _read("netbox_proxbox/api/views.py")
    assert "ProxmoxDatacenterCpuModelViewSet" in content


def test_datacenter_route_registered_in_api_urls():
    content = _read("netbox_proxbox/api/urls.py")
    assert "datacenter-cpu-models" in content
    assert "proxmoxdatacentercpumodel" in content


# ---------------------------------------------------------------------------
# Sync service
# ---------------------------------------------------------------------------


def test_sync_datacenter_service_file_exists():
    assert (REPO_ROOT / "netbox_proxbox/services/sync_datacenter.py").exists()


def test_sync_datacenter_service_defines_sync_function():
    content = _read("netbox_proxbox/services/sync_datacenter.py")
    assert "def sync_datacenter" in content


def test_sync_datacenter_service_fetches_cpu_models_route():
    content = _read("netbox_proxbox/services/sync_datacenter.py")
    assert "/proxmox/datacenter/cpu-models" in content


def test_sync_datacenter_service_has_result_dataclass():
    content = _read("netbox_proxbox/services/sync_datacenter.py")
    assert "DatacenterSyncResult" in content
    assert "cpu_models_created" in content


# ---------------------------------------------------------------------------
# ProxmoxNode location field
# ---------------------------------------------------------------------------


def test_proxmox_node_has_location_field():
    content = _read("netbox_proxbox/models/proxmox_node.py")
    assert "location" in content


def test_proxmox_node_location_is_optional():
    content = _read("netbox_proxbox/models/proxmox_node.py")
    assert "blank=True" in content
