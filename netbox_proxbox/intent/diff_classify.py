"""Classify one VM resolved from the combined VM and intent diff streams."""

from __future__ import annotations

from typing import Any

from netbox_proxbox.vm_identity import resolve_known_vm_type

_INTENT_ACTIONS = {"create", "update", "delete"}


def _contains_lxc_marker(value: Any) -> bool:
    text = str(value or "").lower()
    return "lxc" in text or "container" in text


def _role_markers(vm: Any) -> list[Any]:
    markers: list[Any] = []
    for attr in ("virtual_machine_type", "role"):
        obj = getattr(vm, attr, None)
        if obj is None:
            continue
        markers.extend((getattr(obj, "slug", None), getattr(obj, "name", None)))
    return markers


def _snapshot_dict(change_diff: Any, attribute: str) -> dict[str, Any]:
    data = getattr(change_diff, attribute, None)
    return data if isinstance(data, dict) else {}


def _snapshot_kind(data: dict[str, Any]) -> str:
    sync_state = data.get("proxbox_sync_state")
    if isinstance(sync_state, dict):
        value = sync_state.get("proxmox_vm_type")
        if value not in (None, ""):
            return "lxc" if _contains_lxc_marker(value) else "qemu"

    markers: list[Any] = []
    for key in ("virtual_machine_type", "role"):
        value = data.get(key)
        if isinstance(value, dict):
            markers.extend((value.get("slug"), value.get("name")))
        else:
            markers.append(value)
    markers.extend(
        data.get(key) for key in ("virtual_machine_type_slug", "role_slug", "role_name")
    )
    return "lxc" if any(_contains_lxc_marker(value) for value in markers) else ""


def _classify_kind(vm: Any, change_diff: Any = None) -> str:
    kind = resolve_known_vm_type(vm)
    if kind:
        return kind
    if any(_contains_lxc_marker(marker) for marker in _role_markers(vm)):
        return "lxc"
    for attribute in ("original", "current"):
        kind = _snapshot_kind(_snapshot_dict(change_diff, attribute))
        if kind:
            return kind
    return "qemu"


def classify_diff(vm: Any, op: str, change_diff: Any = None) -> tuple[str, str]:
    """Return normalized ``(op, kind)`` using the VM or retained ChangeDiff."""
    normalized_op = str(op or "").lower()
    if normalized_op not in _INTENT_ACTIONS:
        normalized_op = "update"
    return normalized_op, _classify_kind(vm, change_diff)


__all__ = ("classify_diff",)
