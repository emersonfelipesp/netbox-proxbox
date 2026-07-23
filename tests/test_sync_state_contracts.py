"""Source contracts for typed Proxbox sync-state sidecars."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


SYNC_STATE_MODELS = (
    "ProxboxVirtualMachineSyncState",
    "ProxboxDeviceSyncState",
    "ProxboxClusterSyncState",
    "ProxboxIPAddressSyncState",
    "ProxboxInterfaceSyncState",
    "ProxboxVLANSyncState",
    "ProxboxClusterGroupSyncState",
    "ProxboxVirtualDiskSyncState",
    "ProxboxVMInterfaceSyncState",
    "ProxboxDeviceRoleSyncState",
    "ProxboxDeviceTypeSyncState",
    "ProxboxManufacturerSyncState",
    "ProxboxSiteSyncState",
    "ProxboxClusterTypeSyncState",
)


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text()


def _read_migration(suffix: str) -> str:
    """Read a migration by name suffix, ignoring its sequence number.

    Migrations get renumbered to keep the graph linear when two branches land
    the same sequence number, and a hard-coded ``00NN_`` path in a test breaks
    on the rename even though nothing about the contract changed.
    """
    matches = sorted(
        (REPO_ROOT / "netbox_proxbox" / "migrations").glob(f"*_{suffix}.py")
    )
    assert matches, f"no migration matching *_{suffix}.py"
    assert len(matches) == 1, f"ambiguous migration for *_{suffix}.py: {matches}"
    return matches[0].read_text()


def test_sync_state_model_surface_exists() -> None:
    content = _read("netbox_proxbox/models/sync_state.py")
    assert "class ProxboxSyncStateBase(NetBoxModel)" in content
    assert "abstract = True" in content
    assert "\n    last_updated = models.DateTimeField" not in content
    assert "proxmox_last_updated = models.DateTimeField" in content
    assert "last_run_id = models.CharField" in content
    assert 'to="netbox_proxbox.ProxmoxEndpoint"' in content
    assert 'to="netbox_proxbox.ProxmoxNode"' in content
    assert 'to="netbox_proxbox.ProxmoxCluster"' in content
    assert "proxmox_node_name" in content
    assert "proxmox_cluster_name" in content
    assert "proxmox_endpoint_raw_id" in content
    assert "proxmox_cluster_raw_id" in content
    assert "proxbox_storage_raw_value" in content
    assert "proxbox_bridge_raw_value" in content
    assert "proxmox_endpoint_id = models.IntegerField" not in content
    assert "proxmox_cluster_id = models.IntegerField" not in content
    for model_name in SYNC_STATE_MODELS:
        assert f"class {model_name}" in content


def test_sync_state_models_exported() -> None:
    content = _read("netbox_proxbox/models/__init__.py")
    for model_name in (*SYNC_STATE_MODELS, "ProxboxSyncStateBase"):
        assert model_name in content
        assert f'"{model_name}"' in content


def test_sync_state_api_wiring() -> None:
    serializers = _read("netbox_proxbox/api/serializers/sync_state.py")
    serializers_init = _read("netbox_proxbox/api/serializers/__init__.py")
    views = _read("netbox_proxbox/api/views.py")
    urls = _read("netbox_proxbox/api/urls.py")
    assert "class RestrictedNestedObjectMixin" in serializers
    assert "class RestrictedNestedProxmoxStorageSerializer" in serializers
    assert 'queryset.restrict(user, "view")' in serializers
    assert "def to_representation(self, instance)" in serializers
    assert "_proxbox_nested_visibility_cache" in serializers
    assert "_proxbox_nested_visibility_pk_cache" in serializers
    assert "pk__in=candidate_ids" in serializers
    assert "node.netbox_device_id != parent.pk" in serializers
    assert "cluster.netbox_cluster_id != parent.pk" in serializers
    assert "proxbox_storage = RestrictedNestedProxmoxStorageSerializer" in serializers
    assert "class _ParentRestrictedSyncStateViewSetMixin" in views
    assert "class _RelationRestrictedSyncStateViewSetMixin" in views
    assert 'parent_queryset.restrict(user, "view")' in views
    assert 'restricted_relation_fields = ("proxbox_storage",)' in views
    assert 'restricted_relation_fields = ("proxbox_bridge",)' in views
    for model_name in SYNC_STATE_MODELS:
        assert f"{model_name}Serializer" in serializers
        assert f"{model_name}Serializer" in serializers_init
        assert f"{model_name}ViewSet" in views
        assert f"{model_name}FilterSet" in views
    for route in (
        "sync-state/virtual-machines",
        "sync-state/devices",
        "sync-state/clusters",
        "sync-state/ip-addresses",
        "sync-state/interfaces",
        "sync-state/vlans",
        "sync-state/cluster-groups",
        "sync-state/virtual-disks",
        "sync-state/vm-interfaces",
        "sync-state/device-roles",
        "sync-state/device-types",
        "sync-state/manufacturers",
        "sync-state/sites",
        "sync-state/cluster-types",
    ):
        assert route in urls
    assert 'response.data["sync_state"]' in views


def test_sync_state_filtersets_and_tables_exist() -> None:
    filtersets = _read("netbox_proxbox/filtersets.py")
    tables = _read("netbox_proxbox/tables/sync_state.py")
    tables_init = _read("netbox_proxbox/tables/__init__.py")
    for model_name in SYNC_STATE_MODELS:
        assert f"class {model_name}FilterSet" in filtersets
        assert f"class {model_name}Table" in tables
        assert f"{model_name}Table" in tables_init


def test_sync_state_migrations_pin_schema_and_backfill() -> None:
    idempotent_ops = _read("netbox_proxbox/migrations/_idempotent_ops.py")
    schema = _read("netbox_proxbox/migrations/0065_proxbox_sync_state_models.py")
    backfill = _read("netbox_proxbox/migrations/0066_backfill_proxbox_sync_state.py")
    relation_schema = _read("netbox_proxbox/migrations/0067_sync_state_relation_fks.py")
    relation_data = _read(
        "netbox_proxbox/migrations/0068_sync_state_relation_fk_data.py"
    )
    relation_cleanup = _read(
        "netbox_proxbox/migrations/0069_sync_state_relation_fk_cleanup.py"
    )
    for model_name in SYNC_STATE_MODELS:
        assert f'name="{model_name}"' in schema
        assert f'"{model_name}"' in backfill
    assert "create_model_idempotent" in schema
    assert "ProjectState.from_apps(apps)" in idempotent_ops
    assert "migrations.CreateModel(**state_kwargs).state_forwards" in idempotent_ops
    assert "_model_from_create_state" in idempotent_ops
    assert "_live_model" not in idempotent_ops
    assert "backfill_proxbox_sync_state" in backfill
    assert "reverse_backfill_proxbox_sync_state" in backfill
    assert "apps.get_model" in backfill
    assert "update_or_create" in backfill
    assert "row_failures" in backfill
    assert "_raise_row_failures(row_failures)" in backfill
    assert "custom_field_data" in backfill
    assert "cf_{name}" in backfill
    assert "proxmox_last_updated" in schema
    assert "proxmox_endpoint_raw_id" in schema
    assert "proxmox_cluster_raw_id" in schema
    assert "ProxmoxEndpoint.objects.filter(pk=endpoint_id)" not in backfill
    assert 'order_by("pk").first()' not in backfill
    assert ".objects.all().delete()" not in backfill
    assert "delete rows it may not have created" in backfill
    assert '"proxmox_cluster_raw_id": ("proxmox_cluster_id", "int")' in backfill

    assert "add_field_idempotent" in relation_schema
    assert "atomic = False" in relation_schema
    assert "migrations.RenameField" not in relation_schema
    assert "migrations.RemoveField" not in relation_schema
    assert 'field_name="proxbox_storage_fk"' in relation_schema
    assert 'field_name="proxbox_storage_raw_id"' in relation_schema
    assert 'field_name="proxbox_storage_raw_value"' in relation_schema
    assert 'field_name="proxbox_bridge_fk"' in relation_schema
    assert 'field_name="proxbox_bridge_raw_id"' in relation_schema
    assert 'field_name="proxbox_bridge_raw_value"' in relation_schema
    assert 'to="netbox_proxbox.proxmoxstorage"' in relation_schema
    assert 'to="dcim.interface"' in relation_schema

    assert "atomic = False" in relation_data
    assert "convert_sync_state_relation_fks" in relation_data
    assert "restore_legacy_relation_values" in relation_data
    assert "value = getattr(obj, fk_attname)" in relation_data
    assert "raw_id not in existing_raw_ids" in relation_data
    assert "_save_relation_conversion" in relation_data
    assert "BIGINT_MIN = -(2**63)" in relation_data
    assert "BIGINT_MAX = 2**63 - 1" in relation_data
    assert "RelationTarget.objects.filter(pk__in=candidate_ids)" in relation_data
    assert "set(Storage.objects.values_list" not in relation_data
    assert "set(Interface.objects.values_list" not in relation_data
    assert "bulk_update" not in relation_data

    assert "assert_relation_values_preserved" in relation_cleanup
    assert 'name="proxbox_storage_id"' in relation_cleanup
    assert 'old_name="proxbox_storage_fk"' in relation_cleanup
    assert 'new_name="proxbox_storage"' in relation_cleanup
    assert 'name="proxbox_bridge"' in relation_cleanup
    assert 'old_name="proxbox_bridge_fk"' in relation_cleanup
    assert 'new_name="proxbox_bridge"' in relation_cleanup


def test_vm_sync_state_records_last_synced_proxmox_name() -> None:
    """`proxmox_vm_name` must exist end to end (netbox-proxbox issue #617).

    A VM renamed in Proxmox never had that rename written back to NetBox.
    proxbox-api's name-collision resolver treats any mismatch between the stored
    NetBox name and the incoming Proxmox name as "an operator renamed this inside
    NetBox" and pushes the stale name back onto the payload — a heuristic that
    cannot be right, because both situations look identical from its inputs.

    Persisting the name Proxmox last reported supplies the missing third data
    point:

        stored name != proxmox_vm_name         -> edited in NetBox -> preserve
        stored name == proxmox_vm_name != new  -> renamed in Proxmox -> update

    The field is only useful if the backend can both read and write it, so pin
    the model field, the migration, and the serializer surface together.
    """
    model_source = _read("netbox_proxbox/models/sync_state.py")
    assert "proxmox_vm_name = models.CharField" in model_source, (
        "ProxboxVirtualMachineSyncState must persist the last-synced Proxmox name"
    )

    migration = _read_migration("sync_state_proxmox_vm_name")
    assert "proxboxvirtualmachinesyncstate" in migration
    assert 'field_name="proxmox_vm_name"' in migration
    assert "add_field_idempotent" in migration, (
        "follow the repo's idempotent additive-migration pattern"
    )

    serializer_source = _read("netbox_proxbox/api/serializers/sync_state.py")
    assert '"proxmox_vm_name"' in serializer_source, (
        "the field must be exposed over the API — proxbox-api writes it after a "
        "sync and reads it back on the next one"
    )


def test_vm_sync_state_proxmox_name_is_optional() -> None:
    """It must be blank-able, or upgrading would break every existing row.

    Every row starts blank on upgrade, and proxbox-api has to fall back to the
    previous behaviour while it is blank so nothing regresses mid-rollout.
    """
    model_source = _read("netbox_proxbox/models/sync_state.py")
    field_line = next(
        line
        for line in model_source.splitlines()
        if "proxmox_vm_name = models.CharField" in line
    )
    assert "blank=True" in field_line, (
        "proxmox_vm_name must be optional; existing rows have no recorded name"
    )
