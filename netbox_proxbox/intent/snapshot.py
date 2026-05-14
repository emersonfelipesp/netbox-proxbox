"""Metadata snapshots for Proxmox DELETE authorization records."""

from __future__ import annotations

from typing import Any


def _custom_fields(vm: Any) -> dict[str, Any]:
    custom_field_data = getattr(vm, "custom_field_data", None)
    return dict(custom_field_data) if isinstance(custom_field_data, dict) else {}


def _cf_value(custom_fields: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = custom_fields.get(key)
        if value not in (None, ""):
            return value
    return None


def _attr_or_cf(vm: Any, attr_name: str, custom_fields: dict[str, Any], *keys: str) -> Any:
    value = getattr(vm, attr_name, None)
    if value not in (None, ""):
        return value
    return _cf_value(custom_fields, *keys)


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
        "vmid": _int_or_none(
            _attr_or_cf(
                vm,
                "vmid",
                custom_fields,
                "proxmox_vm_id",
                "cf_proxmox_vm_id",
            )
        ),
        "node": _str_or_none(
            _attr_or_cf(
                vm,
                "node",
                custom_fields,
                "proxmox_node",
                "cf_proxmox_node",
            )
        ),
        "name": str(getattr(vm, "name", "") or ""),
        "tags": _tag_names(vm),
        "cores": _int_or_none(getattr(vm, "cores", getattr(vm, "vcpus", None))),
        "memory": _int_or_none(getattr(vm, "memory", None)),
        "disk_gb": _disk_gb(vm),
        "interfaces": _interfaces(vm),
        "ipv4": _ip_string(getattr(vm, "primary_ip4", None)),
        "ipv6": _ip_string(getattr(vm, "primary_ip6", None)),
        "custom_field_data": custom_fields,
    }


__all__ = ("build_metadata_snapshot",)
