"""Payload builders for NetBox -> Proxmox intent apply calls."""

from __future__ import annotations

from typing import Any


def _custom_fields(vm: Any) -> dict[str, Any]:
    cf = getattr(vm, "custom_field_data", None)
    return cf if isinstance(cf, dict) else {}


def _cf_value(cf: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = cf.get(key)
        if value not in (None, ""):
            return value
    return None


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


def _disk_gb(vm: Any) -> int | None:
    total = 0
    found = False
    for disk in _related_all(vm, "virtual_disks"):
        size = _int_or_none(getattr(disk, "size", None))
        if size is None:
            continue
        found = True
        total += size
    return total if found else None


def _tag_names(vm: Any) -> list[str]:
    names: list[str] = []
    for tag in _related_all(vm, "tags"):
        name = getattr(tag, "name", None)
        if name not in (None, ""):
            names.append(str(name))
    return names


def build_vm_payload(vm) -> dict:
    """Build a proxbox-api ``VMIntentPayload`` dictionary from a NetBox VM."""
    cf = _custom_fields(vm)
    return {
        "vmid": _int_or_none(_cf_value(cf, "proxmox_vm_id", "cf_proxmox_vm_id")),
        "name": str(getattr(vm, "name", "") or ""),
        "node": _str_or_none(_cf_value(cf, "proxmox_node", "cf_proxmox_node")),
        "cores": _int_or_none(getattr(vm, "vcpus", None)),
        "memory": _int_or_none(getattr(vm, "memory", None)),
        "disk_gb": _disk_gb(vm),
        "storage": _str_or_none(
            _cf_value(cf, "proxmox_storage", "cf_proxmox_storage")
        ),
        "iso": _str_or_none(_cf_value(cf, "proxmox_iso", "cf_proxmox_iso")),
        "template_vmid": _int_or_none(
            _cf_value(cf, "proxmox_template_vmid", "cf_proxmox_template_vmid")
        ),
        "tags": _tag_names(vm),
        "description": _str_or_none(getattr(vm, "description", None)),
    }


def build_lxc_payload(vm) -> dict:
    """Build a proxbox-api ``LXCIntentPayload`` dictionary from a NetBox VM."""
    cf = _custom_fields(vm)
    return {
        "vmid": _int_or_none(_cf_value(cf, "proxmox_vm_id", "cf_proxmox_vm_id")),
        "name": str(getattr(vm, "name", "") or ""),
        "node": _str_or_none(_cf_value(cf, "proxmox_node", "cf_proxmox_node")),
        "cores": _int_or_none(getattr(vm, "vcpus", None)),
        "memory": _int_or_none(getattr(vm, "memory", None)),
        "swap": _int_or_none(_cf_value(cf, "proxmox_swap", "cf_proxmox_swap")),
        "rootfs": _str_or_none(_cf_value(cf, "proxmox_rootfs", "cf_proxmox_rootfs")),
        "storage": _str_or_none(
            _cf_value(cf, "proxmox_storage", "cf_proxmox_storage")
        ),
        "ostemplate": _str_or_none(
            _cf_value(
                cf,
                "proxmox_ostemplate",
                "cf_proxmox_ostemplate",
                "proxmox_iso",
                "cf_proxmox_iso",
            )
        ),
        "tags": _tag_names(vm),
        "description": _str_or_none(getattr(vm, "description", None)),
    }
