"""Resolve VM and VM-intent ChangeDiff streams into one VM-keyed operation set."""

from __future__ import annotations

from typing import Any

_ACTIONS = {"create", "update", "delete"}
_VM_MODEL = "virtualmachine"
_INTENT_MODEL = "proxmoxvmintent"


def _changed_object(row: Any) -> Any:
    try:
        return getattr(row, "object", None)
    except Exception:  # noqa: BLE001 - deleted generic relation
        return None


def _action(row: Any) -> str | None:
    value = str(getattr(row, "action", "") or "").lower()
    return value if value in _ACTIONS else None


def _json_vm_id(row: Any) -> int | None:
    for attribute in ("original", "modified", "current"):
        data = getattr(row, attribute, None)
        if not isinstance(data, dict):
            continue
        value = data.get("virtual_machine")
        if type(value) is int:  # bool is not a valid foreign-key value
            return value
    return None


def intent_diff_virtual_machine_id(row: Any) -> int | None:
    """Resolve the parent VM ID in the mandatory ChangeDiff fallback order."""
    obj = _changed_object(row)
    value = getattr(obj, "virtual_machine_id", None)
    if type(value) is int:
        return value

    value = _json_vm_id(row)
    if value is not None:
        return value

    object_id = getattr(row, "object_id", None)
    if object_id is None:
        return None
    from netbox_proxbox.models import ProxmoxVMIntent  # noqa: PLC0415

    try:
        intent = ProxmoxVMIntent.objects.get(pk=object_id)
    except ProxmoxVMIntent.DoesNotExist:
        return None
    value = getattr(intent, "virtual_machine_id", None)
    return value if type(value) is int else None


def _vm_for_vm_diff(row: Any) -> Any:
    vm = _changed_object(row)
    if vm is not None:
        return vm
    object_id = getattr(row, "object_id", None)
    if object_id is None:
        return None
    from virtualization.models import VirtualMachine  # noqa: PLC0415

    try:
        return VirtualMachine.objects.get(pk=object_id)
    except VirtualMachine.DoesNotExist:
        return None


def virtual_machine_diff_id(vm: Any, row: Any) -> int | None:
    """Return the core VM primary key without treating it as a Proxmox VMID."""
    value = getattr(vm, "pk", None)
    if type(value) is int:
        return value
    value = getattr(row, "object_id", None)
    return value if type(value) is int else None


def virtual_machine_diff_name(vm: Any, row: Any) -> str:
    """Return the VM display name recorded by the object or its ChangeDiff."""
    value = getattr(vm, "name", None)
    if value not in (None, ""):
        return str(value)
    for attribute in ("original", "current"):
        data = getattr(row, attribute, None)
        if not isinstance(data, dict):
            continue
        value = data.get("name")
        if value not in (None, ""):
            return str(value)
    value = getattr(row, "object_repr", None)
    return str(value) if value not in (None, "") else ""


def _vm_for_intent_diff(row: Any, virtual_machine_id: int) -> Any:
    intent = _changed_object(row)
    vm = getattr(intent, "virtual_machine", None)
    if vm is not None:
        return vm
    from virtualization.models import VirtualMachine  # noqa: PLC0415

    try:
        return VirtualMachine.objects.get(pk=virtual_machine_id)
    except VirtualMachine.DoesNotExist:
        return None


def _rows(branch: Any, model: str) -> Any:
    changediff_qs = getattr(branch, "changediff_set", None)
    if changediff_qs is None:
        return ()
    return changediff_qs.filter(object_type__model=model)


def virtual_machine_diff_union(branch: Any) -> list[tuple[Any, str, Any]]:
    """Return ``(virtual_machine, op, ChangeDiff)`` entries, once per VM.

    A core VM diff supplies its own operation. An intent-only create, update,
    or delete is an update to the corresponding Proxmox guest. When both
    streams contain a row for the same VM, the core VM operation wins. A core
    delete remains present with a ``None`` VM after the generic relation and
    database row disappear; consumers must use its retained ChangeDiff.
    """
    resolved: dict[tuple[str, int], tuple[Any, str, Any]] = {}

    for index, row in enumerate(_rows(branch, _VM_MODEL)):
        op = _action(row)
        if op is None:
            continue
        vm = _vm_for_vm_diff(row)
        vm_id = virtual_machine_diff_id(vm, row)
        if vm_id is not None:
            key = ("vm", vm_id)
        elif op == "delete":
            key = ("deleted-diff", index)
        else:
            continue
        if key not in resolved:
            resolved[key] = (vm, op, row)

    for row in _rows(branch, _INTENT_MODEL):
        if _action(row) is None:
            continue
        vm_id = intent_diff_virtual_machine_id(row)
        key = ("vm", vm_id) if vm_id is not None else None
        if key is None or key in resolved:
            continue
        vm = _vm_for_intent_diff(row, vm_id)
        if vm is not None:
            resolved[key] = (vm, "update", row)

    return list(resolved.values())


__all__ = (
    "intent_diff_virtual_machine_id",
    "virtual_machine_diff_id",
    "virtual_machine_diff_name",
    "virtual_machine_diff_union",
)
