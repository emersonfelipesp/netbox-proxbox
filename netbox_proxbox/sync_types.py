"""Sync type constants, ordering helpers, and error formatting."""

from __future__ import annotations

import json
import re

from netbox_proxbox.choices import SyncTypeChoices

_SDN_SYNC_TYPE = getattr(SyncTypeChoices, "SDN", "sdn")

_SYNC_STAGE_ORDER: tuple[str, ...] = (
    SyncTypeChoices.DEVICES,
    SyncTypeChoices.STORAGE,
    SyncTypeChoices.VIRTUAL_MACHINES,
    SyncTypeChoices.TASK_HISTORY,
    SyncTypeChoices.VIRTUAL_MACHINES_DISKS,
    SyncTypeChoices.VIRTUAL_MACHINES_BACKUPS,
    SyncTypeChoices.VIRTUAL_MACHINES_SNAPSHOTS,
    SyncTypeChoices.NETWORK_INTERFACES,
    SyncTypeChoices.VM_INTERFACES,
    SyncTypeChoices.IP_ADDRESSES,
    _SDN_SYNC_TYPE,
    SyncTypeChoices.REPLICATIONS,
    SyncTypeChoices.BACKUP_ROUTINES,
)

# Maps sync_type choices to the FastAPI backend base path (before ``/stream``).
_SYNC_TYPE_PATH: dict[str, str] = {
    SyncTypeChoices.DEVICES: "dcim/devices/create",
    SyncTypeChoices.STORAGE: "virtualization/virtual-machines/storage/create",
    SyncTypeChoices.VIRTUAL_MACHINES: "virtualization/virtual-machines/create",
    SyncTypeChoices.TASK_HISTORY: "virtualization/virtual-machines/task-history/create",
    SyncTypeChoices.VIRTUAL_MACHINES_BACKUPS: "virtualization/virtual-machines/backups/all/create",
    SyncTypeChoices.VIRTUAL_MACHINES_DISKS: "virtualization/virtual-machines/virtual-disks/create",
    SyncTypeChoices.VIRTUAL_MACHINES_SNAPSHOTS: (
        "virtualization/virtual-machines/snapshots/all/create"
    ),
    SyncTypeChoices.REPLICATIONS: "proxmox/replication",
    SyncTypeChoices.NETWORK_INTERFACES: "dcim/devices/interfaces/create",
    SyncTypeChoices.VM_INTERFACES: "virtualization/virtual-machines/interfaces/create",
    SyncTypeChoices.IP_ADDRESSES: "virtualization/virtual-machines/interfaces/ip-address/create",
    _SDN_SYNC_TYPE: "proxmox/sdn/create",
    SyncTypeChoices.BACKUP_ROUTINES: "proxmox/cluster/backup",
}

# Per-VM path templates used when ``netbox_vm_ids`` is set.  ``{vm_id}`` is
# substituted with each target VM's NetBox primary key before appending ``/stream``.
_VM_SCOPED_PATH_TEMPLATES: dict[str, str] = {
    SyncTypeChoices.VIRTUAL_MACHINES: (
        "virtualization/virtual-machines/{vm_id}/create"
    ),
    SyncTypeChoices.VIRTUAL_MACHINES_DISKS: (
        "virtualization/virtual-machines/{vm_id}/virtual-disks/create"
    ),
    SyncTypeChoices.VIRTUAL_MACHINES_BACKUPS: (
        "virtualization/virtual-machines/{vm_id}/backups/create"
    ),
    SyncTypeChoices.VIRTUAL_MACHINES_SNAPSHOTS: (
        "virtualization/virtual-machines/{vm_id}/snapshots/create"
    ),
}

_ALLOWED_SYNC_SLUGS = frozenset(_SYNC_TYPE_PATH) | {SyncTypeChoices.ALL}

_STAGE_ORDER_INDEX = {t: i for i, t in enumerate(_SYNC_STAGE_ORDER)}

_TARGETED_VM_JOB_NAME_RE = re.compile(r"^Proxbox Sync: Virtual machine (\d+)$")

_TARGETED_VM_SYNC_TYPES: tuple[str, ...] = (
    SyncTypeChoices.VIRTUAL_MACHINES,
    SyncTypeChoices.VIRTUAL_MACHINES_BACKUPS,
    SyncTypeChoices.VIRTUAL_MACHINES_SNAPSHOTS,
)


def _coerce_backend_error_payload(value: object) -> dict[str, object] | None:
    """Return a backend error payload dict when ``value`` is a JSON-encoded object."""
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text.startswith("{"):
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _extract_backend_error_text(payload: dict[str, object]) -> str | None:
    """Extract the most useful human-facing error text from backend payloads."""
    detail = payload.get("detail") or payload.get("message") or payload.get("error")
    if isinstance(detail, str) and detail.strip():
        return detail.strip()
    errors = payload.get("errors")
    if isinstance(errors, list):
        for item in errors:
            if isinstance(item, dict):
                nested = item.get("detail") or item.get("message")
                if isinstance(nested, str) and nested.strip():
                    return nested.strip()
    return None


def _format_stage_sync_error(
    *,
    sync_type: str,
    status: int,
    payload: dict[str, object],
) -> str:
    """Build a user-friendly sync error message for stage failures."""
    raw_text = _extract_backend_error_text(payload) or f"HTTP {status}"
    metadata_payload = _coerce_backend_error_payload(raw_text)
    source_payload = metadata_payload or payload

    backend_error = source_payload.get("error")
    if isinstance(backend_error, str) and backend_error.strip():
        raw_text = backend_error.strip()

    lowered = raw_text.lower()
    postgres_slot_marker = (
        "remaining connection slots are reserved for roles with the superuser attribute"
    )
    if postgres_slot_marker in lowered:
        return (
            f"Stage '{sync_type}' failed (HTTP {status}): "
            "NetBox database is overloaded and has no free PostgreSQL connections for this sync. "
            "Wait for running jobs to finish, then retry. "
            "If this keeps happening, increase PostgreSQL connection capacity or reduce concurrent sync jobs."
        )

    exception_name = source_payload.get("exception")
    if isinstance(exception_name, str) and exception_name.strip():
        raw_text = f"{raw_text} ({exception_name.strip()})"

    return f"Stage '{sync_type}' failed (HTTP {status}): {raw_text}"


def expanded_sync_stages(types: list[str]) -> list[str]:
    """Turn ``[all]`` into every stage in dependency order; pass through explicit lists."""
    if types == [SyncTypeChoices.ALL]:
        return list(_SYNC_STAGE_ORDER)

    expanded = list(types)
    # "Network interfaces" is a user-facing bundle that must reconcile both
    # node interfaces and VM interfaces in dependency order.
    if (
        SyncTypeChoices.NETWORK_INTERFACES in expanded
        and SyncTypeChoices.VM_INTERFACES not in expanded
    ):
        expanded.append(SyncTypeChoices.VM_INTERFACES)
    # IP addresses can only be attached to VM interfaces that already exist in
    # NetBox: the backend's IP stage looks up each Proxmox NIC's interface and
    # silently skips the IP when the interface is missing.  Selecting only the
    # "IP addresses" stage (manually or on a schedule) therefore reconciles
    # nothing when the interfaces are stale/missing.  Auto-append the VM
    # interface stage so interfaces are always reconciled first; stage ordering
    # (``_STAGE_ORDER_INDEX``) guarantees it runs before IP addresses, and the
    # sync-mode cascade still skips both when ``vm_interface`` is disabled.
    if (
        SyncTypeChoices.IP_ADDRESSES in expanded
        and SyncTypeChoices.VM_INTERFACES not in expanded
    ):
        expanded.append(SyncTypeChoices.VM_INTERFACES)

    seen: set[str] = set()
    ordered: list[str] = []
    for sync_type in sorted(expanded, key=lambda t: _STAGE_ORDER_INDEX.get(t, 99)):
        if sync_type in seen:
            continue
        seen.add(sync_type)
        ordered.append(sync_type)
    return ordered


def normalize_sync_types(selected: list[str]) -> list[str]:
    """Deduplicate, drop unknown slugs, order by dependency; ``all`` alone collapses to ``[all]``."""
    uniq: list[str] = []
    seen: set[str] = set()
    for raw in selected:
        s = str(raw).strip()
        if s not in _ALLOWED_SYNC_SLUGS or s in seen:
            continue
        seen.add(s)
        uniq.append(s)
    if not uniq:
        return [SyncTypeChoices.ALL]
    if SyncTypeChoices.ALL in seen:
        return [SyncTypeChoices.ALL]
    return sorted(uniq, key=lambda t: _STAGE_ORDER_INDEX.get(t, 99))


def _sync_stream_path(sync_type: str) -> str:
    """Return proxbox-api SSE path for a scheduled sync type."""
    base = _SYNC_TYPE_PATH.get(sync_type)
    if not base:
        raise ValueError(f"Unknown sync_type: {sync_type!r}")
    return f"{base.rstrip('/')}/stream"


def _sync_stream_paths_for_stage(sync_type: str, netbox_vm_ids: list[str]) -> list[str]:
    """Return one or more SSE paths for a stage, expanding targeted VM runs per VM id."""
    if not netbox_vm_ids:
        return [_sync_stream_path(sync_type)]

    template = _VM_SCOPED_PATH_TEMPLATES.get(sync_type)
    if not template:
        return [_sync_stream_path(sync_type)]

    return [
        f"{template.format(vm_id=vm_id).rstrip('/')}/stream"
        for vm_id in netbox_vm_ids
        if str(vm_id)
    ]


def _format_seconds(seconds: float) -> str:
    """Format elapsed seconds for human-readable stage telemetry."""
    total = max(0, int(seconds))
    mins, secs = divmod(total, 60)
    hours, mins = divmod(mins, 60)
    if hours:
        return f"{hours}h{mins:02d}m{secs:02d}s"
    if mins:
        return f"{mins}m{secs:02d}s"
    return f"{secs}s"
