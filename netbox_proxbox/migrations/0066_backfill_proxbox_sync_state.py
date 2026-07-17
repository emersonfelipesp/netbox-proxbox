"""Backfill typed Proxbox sync-state sidecars from legacy custom fields."""

from __future__ import annotations

import json
import logging

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db import migrations, transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime


LOGGER = logging.getLogger(__name__)
INT32_MIN = -(2**31)
INT32_MAX = 2**31 - 1
_validate_url = URLValidator()


VM_FIELD_MAP = {
    "proxmox_vm_id": ("proxmox_vm_id", "int"),
    "proxmox_vm_type": ("proxmox_vm_type", "text"),
    "proxmox_start_at_boot": ("proxmox_start_at_boot", "bool"),
    "proxmox_unprivileged_container": ("proxmox_unprivileged_container", "bool"),
    "proxmox_qemu_agent": ("proxmox_qemu_agent", "bool"),
    "proxmox_search_domain": ("proxmox_search_domain", "text"),
    "proxmox_link": ("proxmox_link", "text"),
    "proxmox_status": ("proxmox_status", "text"),
    "proxmox_uptime": ("proxmox_uptime", "int"),
    "proxmox_tags": ("proxmox_tags", "text"),
    "proxmox_os": ("proxmox_os", "text"),
    "proxmox_storage": ("proxmox_storage", "text"),
    "proxmox_disk": ("proxmox_disk", "text"),
    "proxmox_interfaces": ("proxmox_interfaces", "text"),
    "proxmox_vmid": ("proxmox_vmid", "text"),
    "proxmox_notes": ("proxmox_notes", "text"),
    "proxmox_tcp_states": ("proxmox_tcp_states", "text"),
    "proxmox_cpu_type": ("proxmox_cpu_type", "text"),
    "proxmox_storage_ids": ("proxmox_storage_ids", "text"),
    "proxmox_storage_names": ("proxmox_storage_names", "text"),
    "proxmox_device_names": ("proxmox_device_names", "text"),
    "proxmox_migration_duration": ("proxmox_migration_duration", "int"),
    "proxmox_migration_type": ("proxmox_migration_type", "text"),
    "proxmox_last_updated": ("proxmox_last_updated", "datetime"),
    "last_run_id": ("proxbox_last_run_id", "text"),
}

DEVICE_FIELD_MAP = {
    "proxmox_link": ("proxmox_link", "text"),
    "proxmox_tags": ("proxmox_tags", "text"),
    "proxmox_os": ("proxmox_os", "text"),
    "proxmox_storage": ("proxmox_storage", "text"),
    "proxmox_disk": ("proxmox_disk", "text"),
    "proxmox_interfaces": ("proxmox_interfaces", "text"),
    "proxmox_vmid": ("proxmox_vmid", "text"),
    "proxmox_notes": ("proxmox_notes", "text"),
    "proxmox_tcp_states": ("proxmox_tcp_states", "text"),
    "proxmox_cpu_type": ("proxmox_cpu_type", "text"),
    "proxmox_storage_ids": ("proxmox_storage_ids", "text"),
    "proxmox_storage_names": ("proxmox_storage_names", "text"),
    "proxmox_device_names": ("proxmox_device_names", "text"),
    "proxmox_last_updated": ("proxmox_last_updated", "datetime"),
    "last_run_id": ("proxbox_last_run_id", "text"),
    "hardware_chassis_serial": ("hardware_chassis_serial", "text"),
    "hardware_chassis_manufacturer": ("hardware_chassis_manufacturer", "text"),
    "hardware_chassis_product": ("hardware_chassis_product", "text"),
}

GENERIC_SPECS = (
    (
        "ipam",
        "IPAddress",
        "ProxboxIPAddressSyncState",
        "ip_address",
        {
            "proxmox_interface": ("proxmox_interface", "text"),
            "proxmox_mac": ("proxmox_mac", "text"),
            "proxmox_ip_addresses": ("proxmox_ip_addresses", "text"),
            "proxmox_last_updated": ("proxmox_last_updated", "datetime"),
        },
    ),
    (
        "dcim",
        "Interface",
        "ProxboxInterfaceSyncState",
        "interface",
        {
            "proxmox_last_updated": ("proxmox_last_updated", "datetime"),
            "nic_speed_gbps": ("nic_speed_gbps", "int"),
            "nic_duplex": ("nic_duplex", "text"),
            "nic_link": ("nic_link", "bool"),
        },
    ),
    (
        "ipam",
        "VLAN",
        "ProxboxVLANSyncState",
        "vlan",
        {
            "proxmox_vlan_id": ("proxmox_vlan_id", "int"),
            "proxmox_last_updated": ("proxmox_last_updated", "datetime"),
        },
    ),
    (
        "virtualization",
        "ClusterGroup",
        "ProxboxClusterGroupSyncState",
        "cluster_group",
        {
            "proxmox_cluster_name": ("proxmox_cluster_name", "text"),
            "proxmox_cluster_status": ("proxmox_cluster_status", "text"),
        },
    ),
    (
        "virtualization",
        "VirtualDisk",
        "ProxboxVirtualDiskSyncState",
        "virtual_disk",
        {
            "proxbox_storage_id": ("proxbox_storage_id", "json"),
            "proxmox_last_updated": ("proxmox_last_updated", "datetime"),
        },
    ),
    (
        "virtualization",
        "VMInterface",
        "ProxboxVMInterfaceSyncState",
        "vm_interface",
        {
            "proxbox_bridge": ("proxbox_bridge", "json"),
            "proxmox_last_updated": ("proxmox_last_updated", "datetime"),
        },
    ),
    (
        "dcim",
        "DeviceRole",
        "ProxboxDeviceRoleSyncState",
        "device_role",
        {"proxmox_last_updated": ("proxmox_last_updated", "datetime")},
    ),
    (
        "dcim",
        "DeviceType",
        "ProxboxDeviceTypeSyncState",
        "device_type",
        {"proxmox_last_updated": ("proxmox_last_updated", "datetime")},
    ),
    (
        "dcim",
        "Manufacturer",
        "ProxboxManufacturerSyncState",
        "manufacturer",
        {"proxmox_last_updated": ("proxmox_last_updated", "datetime")},
    ),
    (
        "dcim",
        "Site",
        "ProxboxSiteSyncState",
        "site",
        {"proxmox_last_updated": ("proxmox_last_updated", "datetime")},
    ),
    (
        "virtualization",
        "ClusterType",
        "ProxboxClusterTypeSyncState",
        "cluster_type",
        {"proxmox_last_updated": ("proxmox_last_updated", "datetime")},
    ),
)

TARGET_MODELS = (
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


def _cf(data: dict, name: str):
    if name in data:
        return data[name]
    return data.get(f"cf_{name}")


def _has_any(data: dict, names: set[str]) -> bool:
    return any(name in data or f"cf_{name}" in data for name in names)


def _to_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list, tuple)):
        try:
            return json.dumps(value, sort_keys=True)
        except TypeError:
            return json.dumps(value, sort_keys=True, default=str)
    return str(value)


def _to_int(value) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (OverflowError, TypeError, ValueError):
        return None


def _to_bool(value) -> bool | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "t", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "f", "no", "n", "off"}:
        return False
    return None


def _to_datetime(value):
    if value in (None, ""):
        return None
    if hasattr(value, "utcoffset"):
        return value
    try:
        parsed = parse_datetime(str(value))
    except (TypeError, ValueError):
        return None
    if parsed is None:
        return None
    if timezone.is_naive(parsed):
        return timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def _is_blank(value) -> bool:
    return value is None or value == ""


def _null_value_for_field(field):
    return "" if getattr(field, "empty_strings_allowed", False) else None


def _convert_json(value, target_label: str, field_name: str):
    if _is_blank(value):
        return None
    try:
        json.dumps(value)
        return value
    except TypeError:
        text = _to_text(value)
        LOGGER.warning(
            "Backfill coerced non-JSON value for %s.%s into a JSON string.",
            target_label,
            field_name,
        )
        return text


def _convert_text(value, field, target_label: str, field_name: str) -> str:
    text = _to_text(value)
    if field.get_internal_type() == "URLField" and text:
        try:
            _validate_url(text)
        except ValidationError:
            LOGGER.warning(
                "Backfill skipped malformed URL for %s.%s: %r",
                target_label,
                field_name,
                text,
            )
            return ""

    max_length = getattr(field, "max_length", None)
    if max_length and len(text) > max_length:
        LOGGER.warning(
            "Backfill truncated %s.%s from %s to %s characters.",
            target_label,
            field_name,
            len(text),
            max_length,
        )
        return text[:max_length]
    return text


def _convert_for_field(Target, field_name: str, value, kind: str):
    field = Target._meta.get_field(field_name)
    target_label = Target._meta.label
    if kind == "int":
        integer = _to_int(value)
        if integer is None:
            return None
        if not INT32_MIN <= integer <= INT32_MAX:
            LOGGER.warning(
                "Backfill skipped out-of-range integer for %s.%s: %r",
                target_label,
                field_name,
                value,
            )
            return None
        return integer
    if kind == "bool":
        return _to_bool(value)
    if kind == "datetime":
        parsed = _to_datetime(value)
        if parsed is None and not _is_blank(value):
            LOGGER.warning(
                "Backfill skipped malformed datetime for %s.%s: %r",
                target_label,
                field_name,
                value,
            )
        return parsed
    if kind == "json":
        return _convert_json(value, target_label, field_name)
    try:
        return _convert_text(value, field, target_label, field_name)
    except Exception as exc:
        LOGGER.warning(
            "Backfill skipped field %s.%s after conversion error: %s",
            target_label,
            field_name,
            exc,
        )
        return _null_value_for_field(field)


def _defaults_from_map(
    Target, data: dict, field_map: dict[str, tuple[str, str]]
) -> dict:
    defaults = {}
    for field_name, (cf_name, kind) in field_map.items():
        try:
            defaults[field_name] = _convert_for_field(
                Target,
                field_name,
                _cf(data, cf_name),
                kind,
            )
        except Exception as exc:
            LOGGER.warning(
                "Backfill skipped field %s.%s: %s",
                Target._meta.label,
                field_name,
                exc,
            )
    return defaults


def _unique_or_none(queryset, label: str):
    matches = list(queryset[:2])
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        LOGGER.warning("Backfill left ambiguous %s unresolved.", label)
    return None


def _resolve_endpoint_from_netbox_cluster(apps, netbox_cluster):
    if netbox_cluster is None:
        return None
    ProxmoxCluster = apps.get_model("netbox_proxbox", "ProxmoxCluster")
    proxmox_cluster = _unique_or_none(
        ProxmoxCluster.objects.filter(netbox_cluster=netbox_cluster),
        f"ProxmoxCluster for NetBox cluster {netbox_cluster!r}",
    )
    return getattr(proxmox_cluster, "endpoint", None)


def _resolve_node_from_netbox_device(apps, netbox_device):
    if netbox_device is None:
        return None
    ProxmoxNode = apps.get_model("netbox_proxbox", "ProxmoxNode")
    return _unique_or_none(
        ProxmoxNode.objects.filter(netbox_device=netbox_device),
        f"ProxmoxNode for NetBox device {netbox_device!r}",
    )


def _resolve_node(apps, raw_name, *, endpoint=None, netbox_device=None):
    strong_node = _resolve_node_from_netbox_device(apps, netbox_device)
    if strong_node is not None:
        return strong_node
    if endpoint is None:
        return None
    name = _to_text(raw_name).strip()
    if not name:
        return None
    ProxmoxNode = apps.get_model("netbox_proxbox", "ProxmoxNode")
    return _unique_or_none(
        ProxmoxNode.objects.filter(endpoint=endpoint, name=name),
        f"ProxmoxNode named {name!r} on endpoint {endpoint!r}",
    )


def _resolve_cluster(apps, raw_name, *, endpoint=None, netbox_cluster=None):
    ProxmoxCluster = apps.get_model("netbox_proxbox", "ProxmoxCluster")
    if netbox_cluster is not None:
        queryset = ProxmoxCluster.objects.filter(netbox_cluster=netbox_cluster)
        if endpoint is not None:
            queryset = queryset.filter(endpoint=endpoint)
        strong_cluster = _unique_or_none(
            queryset,
            f"ProxmoxCluster for NetBox cluster {netbox_cluster!r}",
        )
        if strong_cluster is not None:
            return strong_cluster
    if endpoint is None:
        return None
    name = _to_text(raw_name).strip()
    if not name:
        return None
    return _unique_or_none(
        ProxmoxCluster.objects.filter(endpoint=endpoint, name=name),
        f"ProxmoxCluster named {name!r} on endpoint {endpoint!r}",
    )


def _row_failure_message(Target, parent_field: str, parent, exc: Exception) -> str:
    parent_pk = getattr(parent, "pk", None)
    if parent_pk is not None:
        parent_label = f"{parent_field}_id={parent_pk!r}"
    else:
        parent_label = f"{parent_field}={parent!r}"
    return f"{Target._meta.label} parent {parent_label}: {type(exc).__name__}: {exc}"


def _raise_row_failures(row_failures: list[str]) -> None:
    if not row_failures:
        return
    sample = "; ".join(row_failures[:20])
    remaining = len(row_failures) - 20
    if remaining > 0:
        sample = f"{sample}; ... and {remaining} more"
    raise RuntimeError(
        "Backfill failed to create "
        f"{len(row_failures)} sync-state sidecar row(s): {sample}"
    )


def _save_sidecar(
    Target,
    parent_field: str,
    parent,
    defaults: dict,
    row_failures: list[str],
) -> None:
    lookup = {parent_field: parent}
    try:
        with transaction.atomic():
            Target.objects.update_or_create(
                **lookup,
                defaults=defaults,
            )
        return
    except Exception as exc:
        LOGGER.warning(
            "Backfill retrying %s for %s=%r field-by-field after save error: %s",
            Target._meta.label,
            parent_field,
            parent,
            exc,
        )

    try:
        with transaction.atomic():
            obj, _created = Target.objects.get_or_create(**lookup)
    except Exception as exc:
        message = _row_failure_message(Target, parent_field, parent, exc)
        LOGGER.error(
            "Backfill could not create base sidecar row; migration will fail "
            "after remaining objects are checked: %s",
            message,
        )
        row_failures.append(message)
        return

    for field_name, value in defaults.items():
        try:
            with transaction.atomic():
                setattr(obj, field_name, value)
                obj.save(update_fields=[field_name])
        except Exception as exc:
            LOGGER.warning(
                "Backfill skipped field %s.%s for %s=%r: %s",
                Target._meta.label,
                field_name,
                parent_field,
                parent,
                exc,
            )
            try:
                obj.refresh_from_db()
            except Exception:
                pass


def _backfill_virtual_machines(apps, row_failures: list[str]) -> None:
    VirtualMachine = apps.get_model("virtualization", "VirtualMachine")
    Target = apps.get_model("netbox_proxbox", "ProxboxVirtualMachineSyncState")
    cf_names = {cf_name for cf_name, _kind in VM_FIELD_MAP.values()} | {
        "proxmox_node",
        "proxmox_cluster",
        "proxmox_endpoint_id",
    }
    for vm in VirtualMachine.objects.all().iterator():
        data = getattr(vm, "custom_field_data", None) or {}
        if not _has_any(data, cf_names):
            continue
        netbox_cluster = getattr(vm, "cluster", None)
        cluster = _resolve_cluster(
            apps,
            _cf(data, "proxmox_cluster"),
            netbox_cluster=netbox_cluster,
        )
        endpoint = getattr(cluster, "endpoint", None)
        if endpoint is None:
            endpoint = _resolve_endpoint_from_netbox_cluster(apps, netbox_cluster)
        node = _resolve_node(apps, _cf(data, "proxmox_node"), endpoint=endpoint)
        if cluster is None:
            cluster = _resolve_cluster(
                apps,
                _cf(data, "proxmox_cluster"),
                endpoint=endpoint,
                netbox_cluster=netbox_cluster,
            )
        defaults = _defaults_from_map(Target, data, VM_FIELD_MAP)
        defaults.update(
            {
                "endpoint": endpoint,
                "proxmox_node": node,
                "proxmox_node_name": _convert_for_field(
                    Target,
                    "proxmox_node_name",
                    _cf(data, "proxmox_node"),
                    "text",
                ),
                "proxmox_cluster": cluster,
                "proxmox_cluster_name": _convert_for_field(
                    Target,
                    "proxmox_cluster_name",
                    _cf(data, "proxmox_cluster"),
                    "text",
                ),
                "proxmox_endpoint_raw_id": _convert_for_field(
                    Target,
                    "proxmox_endpoint_raw_id",
                    _cf(data, "proxmox_endpoint_id"),
                    "int",
                ),
            }
        )
        _save_sidecar(Target, "virtual_machine", vm, defaults, row_failures)


def _backfill_devices(apps, row_failures: list[str]) -> None:
    Device = apps.get_model("dcim", "Device")
    Target = apps.get_model("netbox_proxbox", "ProxboxDeviceSyncState")
    cf_names = {cf_name for cf_name, _kind in DEVICE_FIELD_MAP.values()} | {
        "proxmox_node",
        "proxmox_cluster",
    }
    for device in Device.objects.all().iterator():
        data = getattr(device, "custom_field_data", None) or {}
        if not _has_any(data, cf_names):
            continue
        node = _resolve_node(
            apps,
            _cf(data, "proxmox_node"),
            netbox_device=device,
        )
        endpoint = getattr(node, "endpoint", None) if node is not None else None
        netbox_cluster = getattr(device, "cluster", None)
        cluster = _resolve_cluster(
            apps,
            _cf(data, "proxmox_cluster"),
            endpoint=endpoint,
            netbox_cluster=netbox_cluster,
        )
        if endpoint is None and cluster is not None:
            endpoint = getattr(cluster, "endpoint", None)
        if node is None:
            node = _resolve_node(apps, _cf(data, "proxmox_node"), endpoint=endpoint)
        if cluster is None:
            cluster = _resolve_cluster(
                apps,
                _cf(data, "proxmox_cluster"),
                endpoint=endpoint,
                netbox_cluster=netbox_cluster,
            )
        defaults = _defaults_from_map(Target, data, DEVICE_FIELD_MAP)
        defaults.update(
            {
                "endpoint": endpoint,
                "proxmox_node": node,
                "proxmox_node_name": _convert_for_field(
                    Target,
                    "proxmox_node_name",
                    _cf(data, "proxmox_node"),
                    "text",
                ),
                "proxmox_cluster": cluster,
                "proxmox_cluster_name": _convert_for_field(
                    Target,
                    "proxmox_cluster_name",
                    _cf(data, "proxmox_cluster"),
                    "text",
                ),
            }
        )
        _save_sidecar(Target, "device", device, defaults, row_failures)


def _backfill_clusters(apps, row_failures: list[str]) -> None:
    Cluster = apps.get_model("virtualization", "Cluster")
    Target = apps.get_model("netbox_proxbox", "ProxboxClusterSyncState")
    field_map = {
        "proxmox_cluster_name": ("proxmox_cluster_name", "text"),
        "proxmox_cluster_status": ("proxmox_cluster_status", "text"),
        "proxmox_cluster_raw_id": ("proxmox_cluster_id", "int"),
        "proxmox_last_updated": ("proxmox_last_updated", "datetime"),
        "last_run_id": ("proxbox_last_run_id", "text"),
    }
    cf_names = {cf_name for cf_name, _kind in field_map.values()}
    for cluster in Cluster.objects.all().iterator():
        data = getattr(cluster, "custom_field_data", None) or {}
        if not _has_any(data, cf_names):
            continue
        proxmox_cluster = _resolve_cluster(
            apps,
            _cf(data, "proxmox_cluster_name"),
            netbox_cluster=cluster,
        )
        defaults = _defaults_from_map(Target, data, field_map)
        defaults["proxmox_cluster"] = proxmox_cluster
        _save_sidecar(Target, "cluster", cluster, defaults, row_failures)


def _backfill_generic(
    apps,
    app_label,
    source_model,
    target_model,
    parent_field,
    field_map,
    row_failures: list[str],
):
    Source = apps.get_model(app_label, source_model)
    Target = apps.get_model("netbox_proxbox", target_model)
    cf_names = {cf_name for cf_name, _kind in field_map.values()}
    for obj in Source.objects.all().iterator():
        data = getattr(obj, "custom_field_data", None) or {}
        if not _has_any(data, cf_names):
            continue
        _save_sidecar(
            Target,
            parent_field,
            obj,
            _defaults_from_map(Target, data, field_map),
            row_failures,
        )


def backfill_proxbox_sync_state(apps, schema_editor) -> None:
    row_failures: list[str] = []
    _backfill_virtual_machines(apps, row_failures)
    _backfill_devices(apps, row_failures)
    _backfill_clusters(apps, row_failures)
    for spec in GENERIC_SPECS:
        _backfill_generic(apps, *spec, row_failures)
    _raise_row_failures(row_failures)


def reverse_backfill_proxbox_sync_state(apps, schema_editor) -> None:
    # Legacy custom fields remain the parallel source of truth during this
    # additive phase. A full rollback reverses schema migration 0065, which
    # drops the sidecar tables. Reversing only this data migration must never
    # delete rows it may not have created, such as API edits or pre-existing
    # sidecars.
    return None


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0065_proxbox_sync_state_models"),
    ]

    operations = [
        migrations.RunPython(
            backfill_proxbox_sync_state,
            reverse_backfill_proxbox_sync_state,
        ),
    ]
