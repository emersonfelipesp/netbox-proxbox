"""ChangeDiff classification helpers for Proxmox intent apply jobs."""

from __future__ import annotations

from typing import Any

_INTENT_ACTIONS = {"create", "update", "delete"}


def _changed_object(change_diff: Any) -> Any:
    try:
        return getattr(change_diff, "object", None)
    except Exception:  # noqa: BLE001
        return None


def _data_dict(change_diff: Any, attr: str) -> dict[str, Any] | None:
    data = getattr(change_diff, attr, None)
    return data if isinstance(data, dict) else None


def _classify_op(change_diff: Any) -> str:
    action = str(getattr(change_diff, "action", "") or "").lower()
    if action in _INTENT_ACTIONS:
        return action

    prechange_data = _data_dict(change_diff, "prechange_data")
    postchange_data = _data_dict(change_diff, "postchange_data")
    if prechange_data is None and postchange_data is not None:
        return "create"
    if prechange_data is not None and postchange_data is None:
        return "delete"
    return "update"


def _custom_fields_from_vm(vm: Any) -> dict[str, Any]:
    cf = getattr(vm, "custom_field_data", None)
    return cf if isinstance(cf, dict) else {}


def _custom_fields_from_data(data: dict[str, Any] | None) -> dict[str, Any]:
    if not data:
        return {}
    for key in ("custom_field_data", "custom_fields"):
        cf = data.get(key)
        if isinstance(cf, dict):
            return cf
    return {}


def _contains_lxc_marker(value: Any) -> bool:
    text = str(value or "").lower()
    return "lxc" in text or "container" in text


def _kind_from_custom_fields(cf: dict[str, Any]) -> str | None:
    for key in (
        "proxmox_vm_type",
        "cf_proxmox_vm_type",
        "proxmox_type",
        "cf_proxmox_type",
        "proxmox_kind",
        "cf_proxmox_kind",
    ):
        value = cf.get(key)
        if value in (None, ""):
            continue
        if _contains_lxc_marker(value):
            return "lxc"
        return "qemu"
    return None


def _role_markers_from_vm(vm: Any) -> list[Any]:
    markers: list[Any] = []
    for attr in ("virtual_machine_type", "role"):
        obj = getattr(vm, attr, None)
        if obj is None:
            continue
        markers.append(getattr(obj, "slug", None))
        markers.append(getattr(obj, "name", None))
    return markers


def _role_markers_from_data(data: dict[str, Any] | None) -> list[Any]:
    if not data:
        return []

    markers: list[Any] = []
    for key in ("virtual_machine_type", "role"):
        value = data.get(key)
        if isinstance(value, dict):
            markers.append(value.get("slug"))
            markers.append(value.get("name"))
        else:
            markers.append(value)

    for key in ("virtual_machine_type_slug", "role_slug", "role_name"):
        markers.append(data.get(key))

    return markers


def _classify_kind(change_diff: Any) -> str:
    vm = _changed_object(change_diff)
    postchange_data = _data_dict(change_diff, "postchange_data")
    prechange_data = _data_dict(change_diff, "prechange_data")
    data = postchange_data or prechange_data

    kind = _kind_from_custom_fields(_custom_fields_from_vm(vm))
    if kind is not None:
        return kind

    kind = _kind_from_custom_fields(_custom_fields_from_data(data))
    if kind is not None:
        return kind

    markers = _role_markers_from_vm(vm) + _role_markers_from_data(data)
    if any(_contains_lxc_marker(marker) for marker in markers):
        return "lxc"
    return "qemu"


def classify_diff(change_diff) -> tuple[str, str]:
    """Return ``(op, kind)`` for a netbox-branching ChangeDiff row."""
    return _classify_op(change_diff), _classify_kind(change_diff)
