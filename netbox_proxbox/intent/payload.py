"""Payload builders for NetBox -> Proxmox intent apply calls."""

from __future__ import annotations

import json
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


def _cloud_init_text(value: Any) -> Any:
    if value in (None, ""):
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return value


def _cloud_init_ssh_keys(value: Any) -> list[str] | None:
    text = _cloud_init_text(value)
    if text is None:
        return None
    keys = [line.strip() for line in str(text).splitlines() if line.strip()]
    return keys or None


def _cloud_init_network(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value or None
    text = _cloud_init_text(value)
    if text is None:
        return None
    try:
        parsed = json.loads(str(text))
    except (TypeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) and parsed else None


def _cloud_init_payload(cf: dict[str, Any]) -> dict[str, Any] | None:
    cloud_init: dict[str, Any] = {}

    user = _str_or_none(_cf_value(cf, "cloud_init_user"))
    if user is not None:
        cloud_init["user"] = user

    ssh_keys = _cloud_init_ssh_keys(_cf_value(cf, "cloud_init_ssh_keys"))
    if ssh_keys is not None:
        cloud_init["ssh_keys"] = ssh_keys

    user_data = _cloud_init_text(_cf_value(cf, "cloud_init_user_data"))
    if user_data is not None:
        cloud_init["user_data"] = user_data

    network = _cloud_init_network(_cf_value(cf, "cloud_init_network"))
    if network is not None:
        cloud_init["network"] = network

    return cloud_init or None


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
    payload = {
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
    cloud_init = _cloud_init_payload(cf)
    if cloud_init is not None:
        payload["cloud_init"] = cloud_init
    return payload


def build_lxc_payload(vm) -> dict:
    """Build a proxbox-api ``LXCIntentPayload`` dictionary from a NetBox VM."""
    cf = _custom_fields(vm)
    payload = {
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
    cloud_init = _cloud_init_payload(cf)
    if cloud_init is not None:
        payload["cloud_init"] = cloud_init
    return payload


def build_update_delta(vm, prev_state: dict) -> dict:
    """Return only the payload fields that changed vs ``prev_state``.

    The result always includes ``vmid`` and ``node`` so the backend can route
    the request; an empty result (after stripping routing keys) means no real
    change and the caller should skip the dispatch.
    """
    prev = prev_state if isinstance(prev_state, dict) else {}
    kind_hint = str(prev.get("kind") or "").lower()
    builder = build_lxc_payload if kind_hint == "lxc" else build_vm_payload
    current = builder(vm)

    delta: dict[str, Any] = {}
    for key, new_value in current.items():
        if key in ("vmid", "node"):
            continue
        if prev.get(key) != new_value:
            delta[key] = new_value

    if not delta:
        return {}

    delta["vmid"] = current.get("vmid")
    delta["node"] = current.get("node")
    return delta
