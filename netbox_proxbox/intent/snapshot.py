"""Metadata snapshots for Proxmox DELETE authorization records."""

from __future__ import annotations

from typing import Any

from netbox_proxbox.vm_identity import resolve_vm_node, resolve_vm_vmid

_INTENT_FIELDS = (
    "target_node",
    "target_storage",
    "iso",
    "template_vmid",
    "swap",
    "rootfs",
    "ostemplate",
    "cloud_init_user",
    "cloud_init_ssh_keys",
    "cloud_init_user_data",
    "cloud_init_network",
    "intent_state",
    "last_apply_run_id",
)


def _custom_fields(vm: Any) -> dict[str, Any]:
    custom_field_data = getattr(vm, "custom_field_data", None)
    return dict(custom_field_data) if isinstance(custom_field_data, dict) else {}


def _intent_snapshot(vm: Any) -> dict[str, Any]:
    try:
        intent = getattr(vm, "proxbox_intent", None)
    except AttributeError:
        intent = None
    if intent is None:
        return {}
    return {field: getattr(intent, field, None) for field in _INTENT_FIELDS}


def _int_or_none(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


def _str_or_none(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _related_all(vm: Any, relation_name: str) -> list[Any]:
    manager = getattr(vm, relation_name, None)
    if manager is None:
        return []

    all_method = getattr(manager, "all", None)
    try:
        if callable(all_method):
            return list(all_method())
        return list(manager)
    except (TypeError, ValueError):
        return []


def _tag_names(vm: Any) -> list[str]:
    names: list[str] = []
    for tag in _related_all(vm, "tags"):
        name = getattr(tag, "name", None)
        if name not in (None, ""):
            names.append(str(name))
    return names


def _disk_gb(vm: Any) -> int | None:
    value = _int_or_none(getattr(vm, "disk_gb", None))
    if value is not None:
        return value

    total = 0
    found = False
    for disk in _related_all(vm, "virtual_disks"):
        size = _int_or_none(getattr(disk, "size", None))
        if size is None:
            continue
        found = True
        total += size
    return total if found else None


def _interface_snapshot(interface: Any) -> dict[str, Any]:
    if isinstance(interface, dict):
        return dict(interface)

    return {
        "name": _str_or_none(getattr(interface, "name", None)),
        "mac_address": _str_or_none(getattr(interface, "mac_address", None)),
        "enabled": getattr(interface, "enabled", None),
        "mtu": _int_or_none(getattr(interface, "mtu", None)),
        "description": _str_or_none(getattr(interface, "description", None)),
    }


def _interfaces(vm: Any) -> list[dict[str, Any]]:
    interfaces = _related_all(vm, "interfaces")
    if not interfaces:
        interfaces = _related_all(vm, "vminterface_set")
    return [_interface_snapshot(interface) for interface in interfaces]


def _ip_string(value: Any) -> str | None:
    if value in (None, ""):
        return None
    address = getattr(value, "address", None)
    if address not in (None, ""):
        return str(address)
    return str(value)


def build_metadata_snapshot(vm: Any) -> dict[str, Any]:
    """Capture stable VM metadata for a later safe-delete executor."""
    custom_fields = _custom_fields(vm)
    return {
        "vmid": _int_or_none(getattr(vm, "vmid", None) or resolve_vm_vmid(vm)),
        "node": _str_or_none(resolve_vm_node(vm)),
        "name": str(getattr(vm, "name", "") or ""),
        "tags": _tag_names(vm),
        "cores": _int_or_none(getattr(vm, "cores", getattr(vm, "vcpus", None))),
        "memory": _int_or_none(getattr(vm, "memory", None)),
        "disk_gb": _disk_gb(vm),
        "interfaces": _interfaces(vm),
        "ipv4": _ip_string(getattr(vm, "primary_ip4", None)),
        "ipv6": _ip_string(getattr(vm, "primary_ip6", None)),
        "custom_field_data": custom_fields,
        "intent": _intent_snapshot(vm),
    }


def _diff_mapping(change_diff: Any, attribute: str) -> dict[str, Any]:
    data = getattr(change_diff, attribute, None)
    return dict(data) if isinstance(data, dict) else {}


def _recorded_value(snapshots: tuple[dict[str, Any], ...], *keys: str) -> Any:
    for data in snapshots:
        for key in keys:
            value = data.get(key)
            if value not in (None, ""):
                return value
    return None


def _recorded_custom_fields(
    snapshots: tuple[dict[str, Any], ...],
) -> dict[str, Any]:
    for data in snapshots:
        value = data.get("custom_field_data") or data.get("custom_fields")
        if isinstance(value, dict):
            return dict(value)
    return {}


def _recorded_name(value: Any) -> str | None:
    if isinstance(value, dict):
        value = value.get("name")
    return _str_or_none(value)


def build_deleted_metadata_snapshot(change_diff: Any) -> dict[str, Any]:
    """Build deletion metadata solely from a vanished VM's ChangeDiff."""
    original = _diff_mapping(change_diff, "original")
    current = _diff_mapping(change_diff, "current")
    snapshots = (original, current)
    custom_fields = _recorded_custom_fields(snapshots)

    raw_vmid = _recorded_value(snapshots, "vmid")
    vmid = None if type(raw_vmid) is bool else _int_or_none(raw_vmid)
    if vmid is None or vmid <= 0:
        raise ValueError("Deleted VM ChangeDiff does not contain a Proxmox VMID.")

    raw_node = _recorded_value(snapshots, "node")
    node = _recorded_name(raw_node)
    if node is None:
        raise ValueError("Deleted VM ChangeDiff does not contain a Proxmox node.")

    raw_name = _recorded_value(snapshots, "name")
    if raw_name in (None, ""):
        raw_name = getattr(change_diff, "object_repr", None)
    name = _str_or_none(raw_name)
    if name is None:
        raise ValueError("Deleted VM ChangeDiff does not contain a VM name.")

    source = original or current
    tags = source.get("tags")
    interfaces = source.get("interfaces")
    intent = source.get("intent")
    return {
        "vmid": vmid,
        "node": node,
        "name": name,
        "tags": list(tags) if isinstance(tags, (list, tuple)) else [],
        "cores": _int_or_none(source.get("cores", source.get("vcpus"))),
        "memory": _int_or_none(source.get("memory")),
        "disk_gb": _int_or_none(source.get("disk_gb")),
        "interfaces": (
            list(interfaces) if isinstance(interfaces, (list, tuple)) else []
        ),
        "ipv4": _ip_string(source.get("primary_ip4", source.get("ipv4"))),
        "ipv6": _ip_string(source.get("primary_ip6", source.get("ipv6"))),
        "custom_field_data": custom_fields,
        "intent": dict(intent) if isinstance(intent, dict) else {},
        "change_diff": {
            "object_id": getattr(change_diff, "object_id", None),
            "object_repr": getattr(change_diff, "object_repr", None),
            "original": original,
            "current": current or None,
        },
    }


__all__ = ("build_deleted_metadata_snapshot", "build_metadata_snapshot")
