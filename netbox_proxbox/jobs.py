"""Background job for triggering ProxBox sync operations via the FastAPI backend."""

from __future__ import annotations

import asyncio
import json
import re
import time

from netbox.constants import RQ_QUEUE_DEFAULT
from netbox.jobs import JobRunner

from netbox_proxbox.choices import SyncTypeChoices
from netbox_proxbox.schemas import SyncJobData

# Use NetBox's default RQ queue so a stock ``manage.py rqworker`` (no args) picks up jobs.
# Plugin-only queues such as ``netbox_proxbox.sync`` are not in that default worker list.
PROXBOX_SYNC_QUEUE_NAME = RQ_QUEUE_DEFAULT

# Rows created before this change may still have ``queue_name`` set to the legacy queue.
LEGACY_PROXBOX_RQ_QUEUE = "netbox_proxbox.sync"

# RQ wall-clock limit for the whole job. Must exceed NetBox's default ``RQ_DEFAULT_TIMEOUT``
# (often 300s) and the HTTP stream read budget between chunks (3600s in ``run_sync_stream``).
# Override per enqueue via ``job_timeout=...`` if needed.
PROXBOX_SYNC_JOB_TIMEOUT = 7200

# Dependency order for multi-stage syncs (subset runs in this order regardless of UI selection).
_SYNC_STAGE_ORDER: tuple[str, ...] = (
    SyncTypeChoices.DEVICES,
    SyncTypeChoices.STORAGE,
    SyncTypeChoices.VIRTUAL_MACHINES,
    SyncTypeChoices.VIRTUAL_MACHINES_DISKS,
    SyncTypeChoices.VIRTUAL_MACHINES_BACKUPS,
    SyncTypeChoices.VIRTUAL_MACHINES_SNAPSHOTS,
    SyncTypeChoices.NETWORK_INTERFACES,
    SyncTypeChoices.IP_ADDRESSES,
    SyncTypeChoices.BACKUP_ROUTINES,
)

__all__ = (
    "LEGACY_PROXBOX_RQ_QUEUE",
    "PROXBOX_SYNC_QUEUE_NAME",
    "PROXBOX_SYNC_JOB_TIMEOUT",
    "ProxboxSyncJob",
    "is_proxbox_sync_job",
    "normalize_sync_types",
    "proxbox_sync_params_from_job",
)

# Maps sync_type choices to the FastAPI backend base path (before ``/stream``).
_SYNC_TYPE_PATH: dict[str, str] = {
    SyncTypeChoices.DEVICES: "dcim/devices/create",
    SyncTypeChoices.STORAGE: "virtualization/virtual-machines/storage/create",
    SyncTypeChoices.VIRTUAL_MACHINES: "virtualization/virtual-machines/create",
    SyncTypeChoices.VIRTUAL_MACHINES_BACKUPS: "virtualization/virtual-machines/backups/all/create",
    SyncTypeChoices.VIRTUAL_MACHINES_DISKS: "virtualization/virtual-machines/virtual-disks/create",
    SyncTypeChoices.VIRTUAL_MACHINES_SNAPSHOTS: (
        "virtualization/virtual-machines/snapshots/all/create"
    ),
    SyncTypeChoices.NETWORK_INTERFACES: "dcim/devices/interfaces/create",
    SyncTypeChoices.IP_ADDRESSES: "virtualization/virtual-machines/interfaces/ip-address/create",
    SyncTypeChoices.BACKUP_ROUTINES: "cluster/backup",
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


def _use_guest_agent_interface_name_setting() -> bool:
    """Return current plugin setting for guest-agent VM interface naming."""
    try:
        from netbox_proxbox.models import ProxboxPluginSettings

        return bool(ProxboxPluginSettings.get_solo().use_guest_agent_interface_name)
    except Exception:
        return True


def _proxbox_fetch_max_concurrency_setting() -> int:
    """Return fetch concurrency setting for proxbox-api data collection."""
    try:
        from netbox_proxbox.models import ProxboxPluginSettings

        value = int(ProxboxPluginSettings.get_solo().proxbox_fetch_max_concurrency)
        return max(1, value)
    except Exception:
        return 8


def _ignore_ipv6_link_local_addresses_setting() -> bool:
    """Return current plugin setting for ignoring IPv6 link-local addresses."""
    try:
        from netbox_proxbox.models import ProxboxPluginSettings

        return bool(ProxboxPluginSettings.get_solo().ignore_ipv6_link_local_addresses)
    except Exception:
        return True


def expanded_sync_stages(types: list[str]) -> list[str]:
    """Turn ``[all]`` into every stage in dependency order; pass through explicit lists."""
    if types == [SyncTypeChoices.ALL]:
        return list(_SYNC_STAGE_ORDER)
    return types


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


def _serialize_sync_params(
    *,
    sync_types: list[str],
    proxmox_endpoint_ids: list[str],
    netbox_endpoint_ids: list[str],
    netbox_vm_ids: list[str],
    batch_object_type: str | None = None,
    batch_object_ids: list[str] | None = None,
) -> dict[str, object]:
    """Return a backward-compatible params block for Job.data."""
    return {
        "sync_types": list(sync_types),
        # Keep the legacy singular field for older readers that still expect it.
        "sync_type": (
            sync_types[0]
            if len(sync_types) == 1
            else (
                SyncTypeChoices.VIRTUAL_MACHINES
                if netbox_vm_ids
                else SyncTypeChoices.ALL
            )
        ),
        "proxmox_endpoint_ids": list(proxmox_endpoint_ids),
        "netbox_endpoint_ids": list(netbox_endpoint_ids),
        "netbox_vm_ids": list(netbox_vm_ids),
        "batch_object_type": batch_object_type,
        "batch_object_ids": list(batch_object_ids or []),
    }


def _infer_targeted_vm_job_params(job: object) -> dict[str, object] | None:
    """Infer targeted VM params from a legacy job row name when explicit params are absent."""
    name = str(getattr(job, "name", "") or "").strip()
    match = _TARGETED_VM_JOB_NAME_RE.match(name)
    if not match:
        return None
    vm_id = match.group(1)
    return {
        "sync_types": list(_TARGETED_VM_SYNC_TYPES),
        "proxmox_endpoint_ids": [],
        "netbox_endpoint_ids": [],
        "netbox_vm_ids": [vm_id],
    }


def proxbox_sync_params_from_job(job: object) -> dict[str, object]:
    """Rebuild ProxboxSyncJob.enqueue kwargs from job.data (with safe fallbacks)."""
    raw_data = getattr(job, "data", None)
    raw_params = {}
    if isinstance(raw_data, dict):
        raw_block = raw_data.get("proxbox_sync")
        if isinstance(raw_block, dict) and isinstance(raw_block.get("params"), dict):
            raw_params = raw_block["params"]

    data = SyncJobData.from_job(job)
    params = data.params
    if params.sync_types:
        sync_types = normalize_sync_types(params.sync_types)
    elif isinstance(raw_params, dict) and raw_params.get("sync_type"):
        sync_types = normalize_sync_types([str(raw_params.get("sync_type"))])
    else:
        sync_types = [SyncTypeChoices.ALL]
    params = {
        "sync_types": sync_types,
        "proxmox_endpoint_ids": params.proxmox_endpoint_ids,
        "netbox_endpoint_ids": params.netbox_endpoint_ids,
        "netbox_vm_ids": params.netbox_vm_ids,
        "batch_object_type": params.batch_object_type,
        "batch_object_ids": params.batch_object_ids,
    }
    if params["sync_types"] == [SyncTypeChoices.ALL] and not params["netbox_vm_ids"]:
        inferred = _infer_targeted_vm_job_params(job)
        if inferred is not None:
            return inferred
    return params


def _normalize_batch_object_ids(object_ids: list[str] | None) -> list[str]:
    """Return a cleaned list of selected object IDs."""
    return [str(object_id) for object_id in list(object_ids or []) if str(object_id)]


def _resolve_vm_cluster_name(vm: object) -> str:
    """Derive a Proxmox cluster name from a NetBox VM record."""
    from netbox_proxbox.models import ProxmoxCluster

    cluster = getattr(vm, "cluster", None)
    if cluster is None:
        return ""
    proxmox_cluster = ProxmoxCluster.objects.filter(netbox_cluster=cluster).first()
    if proxmox_cluster is not None:
        return str(proxmox_cluster.name)
    return str(getattr(cluster, "name", "") or "")


def _resolve_vm_node(vm: object) -> str:
    """Derive the best-effort Proxmox node name for a NetBox VM."""
    device = getattr(vm, "device", None)
    if device is not None and getattr(device, "name", None):
        return str(device.name)

    custom_field_data = getattr(vm, "custom_field_data", None) or {}
    node = custom_field_data.get("proxmox_node") or custom_field_data.get(
        "cf_proxmox_node", ""
    )
    return str(node or "")


def _resolve_vm_type(vm: object) -> str:
    custom_field_data = getattr(vm, "custom_field_data", None) or {}
    return str(
        custom_field_data.get("proxmox_vm_type")
        or custom_field_data.get("cf_proxmox_vm_type")
        or "qemu"
    )


def _resolve_vm_vmid(vm: object) -> str:
    custom_field_data = getattr(vm, "custom_field_data", None) or {}
    vmid = custom_field_data.get("proxmox_vm_id") or custom_field_data.get(
        "cf_proxmox_vm_id"
    )
    return str(vmid or "")


def _resolve_storage_nodes(storage: object) -> str:
    """Return a best-effort Proxmox node name for a storage-backed row."""
    nodes = getattr(storage, "nodes", None)
    if not nodes:
        return ""
    first = str(nodes).split(",", 1)[0].strip()
    return first


def _resolve_vm_batch_params(vm: object) -> dict[str, object]:
    """Build individual VM sync parameters."""
    cluster_name = _resolve_vm_cluster_name(vm)
    node = _resolve_vm_node(vm)
    vm_type = _resolve_vm_type(vm)
    vmid = _resolve_vm_vmid(vm)
    if not cluster_name or not node or not vmid:
        return {"error": "Missing VM sync context.", "status": 422}
    return {
        "path": "sync/individual/vm",
        "query_params": {
            "cluster_name": cluster_name,
            "node": node,
            "type": vm_type,
            "vmid": vmid,
        },
    }


def _resolve_vm_backup_batch_params(backup: object) -> dict[str, object]:
    """Build individual backup sync parameters."""
    storage_obj = getattr(backup, "proxmox_storage", None)
    vm_obj = getattr(backup, "virtual_machine", None)
    if storage_obj is None or vm_obj is None:
        return {"error": "Missing backup sync context.", "status": 422}

    cluster_name = str(getattr(getattr(storage_obj, "cluster", None), "name", "") or "")
    node = _resolve_storage_nodes(storage_obj) or _resolve_vm_node(vm_obj)
    vmid = str(
        getattr(backup, "vmid", None)
        or getattr(getattr(vm_obj, "custom_field_data", None), "get", lambda *_: None)(
            "proxmox_vm_id"
        )
        or _resolve_vm_vmid(vm_obj)
        or ""
    )
    volume_id = str(getattr(backup, "volume_id", None) or "")
    storage_name = str(
        getattr(backup, "storage", None) or getattr(storage_obj, "name", "") or ""
    )

    if not cluster_name or not node or not vmid or not storage_name or not volume_id:
        return {"error": "Missing backup sync context.", "status": 422}

    return {
        "path": "sync/individual/backup",
        "query_params": {
            "cluster_name": cluster_name,
            "node": node,
            "storage": storage_name,
            "vmid": vmid,
            "volid": volume_id,
        },
    }


def _resolve_vm_snapshot_batch_params(snapshot: object) -> dict[str, object]:
    """Build individual snapshot sync parameters."""
    vm_obj = getattr(snapshot, "virtual_machine", None)
    if vm_obj is None:
        return {"error": "Missing snapshot sync context.", "status": 422}

    cluster_name = _resolve_vm_cluster_name(vm_obj)
    node = str(getattr(snapshot, "node", None) or _resolve_vm_node(vm_obj) or "")
    vm_type = _resolve_vm_type(vm_obj)
    vmid = str(getattr(snapshot, "vmid", None) or _resolve_vm_vmid(vm_obj) or "")
    snapshot_name = str(getattr(snapshot, "name", None) or "")

    if not cluster_name or not node or not vmid or not snapshot_name:
        return {"error": "Missing snapshot sync context.", "status": 422}

    query_params: dict[str, object] = {
        "cluster_name": cluster_name,
        "node": node,
        "type": vm_type,
        "vmid": vmid,
        "snapshot_name": snapshot_name,
    }
    storage_obj = getattr(snapshot, "proxmox_storage", None)
    if storage_obj is not None and getattr(storage_obj, "name", None):
        query_params["storage_name"] = str(storage_obj.name)

    return {"path": "sync/individual/snapshot", "query_params": query_params}


def _resolve_storage_batch_params(storage: object) -> dict[str, object]:
    """Build individual storage sync parameters."""
    cluster = getattr(storage, "cluster", None)
    cluster_name = str(getattr(cluster, "name", "") or "")
    storage_name = str(getattr(storage, "name", None) or "")
    if not cluster_name or not storage_name:
        return {"error": "Missing storage sync context.", "status": 422}

    return {
        "path": "sync/individual/storage",
        "query_params": {
            "cluster_name": cluster_name,
            "storage_name": storage_name,
        },
    }


def _resolve_task_history_batch_params(task_history: object) -> dict[str, object]:
    """Build individual task history sync parameters."""
    vm_obj = getattr(task_history, "virtual_machine", None)
    if vm_obj is None:
        return {"error": "Missing task-history sync context.", "status": 422}

    node = str(getattr(task_history, "node", None) or _resolve_vm_node(vm_obj) or "")
    vm_type = str(
        getattr(task_history, "vm_type", None) or _resolve_vm_type(vm_obj) or "qemu"
    )
    vmid = str(getattr(task_history, "vmid", None) or _resolve_vm_vmid(vm_obj) or "")
    upid = str(getattr(task_history, "upid", None) or "")
    cluster_name = _resolve_vm_cluster_name(vm_obj)

    if not node or not vmid:
        return {"error": "Missing task-history sync context.", "status": 422}

    query_params: dict[str, object] = {
        "node": node,
        "vm_type": vm_type,
        "vmid": vmid,
    }
    if upid:
        query_params["upid"] = upid
    if cluster_name:
        query_params["cluster_name"] = cluster_name

    return {"path": "sync/individual/task-history", "query_params": query_params}


async def _run_batch_selected_sync(
    self,
    *,
    batch_object_type: str,
    batch_object_ids: list[str],
) -> dict[str, object]:
    """Run selected object syncs concurrently with asyncio.gather."""
    from netbox_proxbox.models import (
        ProxmoxStorage,
        VMBackup,
        VMTaskHistory,
        VMSnapshot,
    )
    from virtualization.models import VirtualMachine
    from netbox_proxbox.services.individual_sync import (
        sync_individual_with_dependencies,
    )

    model_map = {
        "virtual-machine": VirtualMachine.objects.select_related(
            "cluster", "device", "site", "role", "tenant", "platform"
        ),
        "vm-backup": VMBackup.objects.select_related(
            "virtual_machine", "proxmox_storage", "proxmox_storage__cluster"
        ),
        "vm-snapshot": VMSnapshot.objects.select_related(
            "virtual_machine", "proxmox_storage", "proxmox_storage__cluster"
        ),
        "proxmox-storage": ProxmoxStorage.objects.select_related("cluster"),
        "vm-task-history": VMTaskHistory.objects.select_related("virtual_machine"),
    }

    queryset = model_map.get(batch_object_type)
    if queryset is None:
        raise ValueError(f"Unsupported batch object type: {batch_object_type!r}")

    object_ids = _normalize_batch_object_ids(batch_object_ids)
    objects = list(queryset.filter(pk__in=object_ids))
    object_by_id = {str(getattr(obj, "pk", "")): obj for obj in objects}

    semaphore = asyncio.Semaphore(_proxbox_fetch_max_concurrency_setting())

    async def run_one(object_id: str) -> dict[str, object]:
        async with semaphore:
            obj = object_by_id.get(str(object_id))
            if obj is None:
                return {
                    "batch_object_type": batch_object_type,
                    "object_id": str(object_id),
                    "status": 404,
                    "error": "Selected object was not found.",
                }

            if batch_object_type == "virtual-machine":
                params = _resolve_vm_batch_params(obj)
            elif batch_object_type == "vm-backup":
                params = _resolve_vm_backup_batch_params(obj)
            elif batch_object_type == "vm-snapshot":
                params = _resolve_vm_snapshot_batch_params(obj)
            elif batch_object_type == "proxmox-storage":
                params = _resolve_storage_batch_params(obj)
            elif batch_object_type == "vm-task-history":
                params = _resolve_task_history_batch_params(obj)
            else:
                return {
                    "batch_object_type": batch_object_type,
                    "object_id": str(object_id),
                    "status": 422,
                    "error": f"Unsupported batch object type: {batch_object_type}",
                }

            if params.get("error"):
                return {
                    "batch_object_type": batch_object_type,
                    "object_id": str(object_id),
                    "status": int(params.get("status") or 422),
                    "error": str(params.get("error")),
                }

            path = str(params["path"])
            query_params = dict(params.get("query_params") or {})

            def _call_sync() -> tuple[dict, int, list[dict]]:
                return sync_individual_with_dependencies(path, query_params)

            response, status, dependencies = await asyncio.to_thread(_call_sync)
            return {
                "batch_object_type": batch_object_type,
                "object_id": str(object_id),
                "status": status,
                "response": response,
                "dependencies": dependencies,
                "error": response.get("error") if isinstance(response, dict) else None,
            }

    results = await asyncio.gather(*(run_one(object_id) for object_id in object_ids))
    succeeded = sum(1 for item in results if int(item.get("status", 500)) < 400)
    failed = len(results) - succeeded
    return {
        "batch_object_type": batch_object_type,
        "batch_object_label": batch_object_type.replace("-", " ").title(),
        "total": len(results),
        "succeeded": succeeded,
        "failed": failed,
        "results": results,
    }


SYNC_OWNER_RQ = "rq_job"


def _claim_rq_sync_ownership(job: object) -> bool:
    """Atomically claim sync ownership for RQ job. Returns True if claimed, False if already taken."""
    import datetime as dt

    raw_data = getattr(job, "data", None)
    if raw_data is None or isinstance(raw_data, dict):
        data = raw_data if raw_data is not None else {}
    elif isinstance(raw_data, str):
        try:
            data = json.loads(raw_data) if raw_data else {}
        except (json.JSONDecodeError, TypeError):
            data = {}
    else:
        data = {}
    proxbox_sync = data.get("proxbox_sync", {})
    current_owner = proxbox_sync.get("sync_owner")
    if current_owner and current_owner != SYNC_OWNER_RQ:
        return False
    proxbox_sync["sync_owner"] = SYNC_OWNER_RQ
    proxbox_sync["sync_owner_claimed_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    data["proxbox_sync"] = proxbox_sync
    job.data = data
    job.save(update_fields=["data"])
    return True


def _release_rq_sync_ownership(job: object) -> None:
    """Release RQ sync ownership if we are the owner."""
    raw_data = getattr(job, "data", None)
    if raw_data is None or isinstance(raw_data, dict):
        data = raw_data if raw_data is not None else {}
    elif isinstance(raw_data, str):
        try:
            data = json.loads(raw_data) if raw_data else {}
        except (json.JSONDecodeError, TypeError):
            data = {}
    else:
        return
    proxbox_sync = data.get("proxbox_sync", {})
    if proxbox_sync.get("sync_owner") == SYNC_OWNER_RQ:
        del proxbox_sync["sync_owner"]
        if proxbox_sync.get("sync_owner_claimed_at"):
            del proxbox_sync["sync_owner_claimed_at"]
        data["proxbox_sync"] = proxbox_sync
        job.data = data
        job.save(update_fields=["data"])


class ProxboxSyncJob(JobRunner):
    """Trigger a ProxBox sync operation against the FastAPI backend."""

    class Meta:
        name = "Proxbox Sync"

    @classmethod
    def enqueue(cls, *args, **kwargs):
        """Enqueue like other ``JobRunner`` jobs, but with a long RQ ``job_timeout`` by default."""
        kwargs.setdefault("job_timeout", PROXBOX_SYNC_JOB_TIMEOUT)
        sync_types_kw = kwargs.pop("sync_types", None)
        sync_type_kw = kwargs.pop("sync_type", None)
        batch_object_type_kw = kwargs.pop("batch_object_type", None)
        batch_object_ids_kw = kwargs.pop("batch_object_ids", None)
        if sync_types_kw is not None:
            normalized = normalize_sync_types(list(sync_types_kw))
        elif sync_type_kw is not None:
            normalized = normalize_sync_types([str(sync_type_kw)])
        else:
            normalized = [SyncTypeChoices.ALL]
        kwargs["sync_types"] = normalized

        batch_object_ids = _normalize_batch_object_ids(batch_object_ids_kw)
        if batch_object_type_kw is not None:
            kwargs["batch_object_type"] = str(batch_object_type_kw)
        if batch_object_ids:
            kwargs["batch_object_ids"] = batch_object_ids

        job = super().enqueue(*args, **kwargs)

        params = {
            "sync_types": normalized,
            "proxmox_endpoint_ids": list(kwargs.get("proxmox_endpoint_ids") or []),
            "netbox_endpoint_ids": list(kwargs.get("netbox_endpoint_ids") or []),
            "netbox_vm_ids": [
                str(x) for x in list(kwargs.get("netbox_vm_ids") or []) if str(x)
            ],
            "batch_object_type": kwargs.get("batch_object_type"),
            "batch_object_ids": [
                str(x) for x in list(kwargs.get("batch_object_ids") or []) if str(x)
            ],
        }
        job.data = {
            "proxbox_sync": {
                "params": _serialize_sync_params(**params),
            }
        }
        job.save(update_fields=["data"])
        return job

    def run(
        self,
        sync_types: list[str] | None = None,
        sync_type: str | None = None,
        proxmox_endpoint_ids: list[str] | None = None,
        netbox_endpoint_ids: list[str] | None = None,
        netbox_vm_ids: list[str] | None = None,
        batch_object_type: str | None = None,
        batch_object_ids: list[str] | None = None,
        **kwargs,
    ):
        """Run one or more proxbox-api SSE streams in dependency order."""
        from netbox_proxbox.services import run_sync_stream

        if not _claim_rq_sync_ownership(self.job):
            self.logger.info(
                "Sync ownership already claimed by SSE stream, RQ job skipping sync execution"
            )
            return

        try:
            if sync_types:
                types = normalize_sync_types([str(x) for x in sync_types])
            elif sync_type is not None:
                types = normalize_sync_types([str(sync_type)])
            else:
                types = [SyncTypeChoices.ALL]

            batch_object_type = (
                str(batch_object_type).strip() if batch_object_type else None
            )
            batch_object_ids = _normalize_batch_object_ids(batch_object_ids)
            run_started = time.monotonic()

            stages = expanded_sync_stages(types)

            params: dict[str, object] = {
                "sync_types": types,
                "proxmox_endpoint_ids": list(proxmox_endpoint_ids or []),
                "netbox_endpoint_ids": list(netbox_endpoint_ids or []),
                "netbox_vm_ids": [str(x) for x in list(netbox_vm_ids or []) if str(x)],
                "batch_object_type": batch_object_type,
                "batch_object_ids": batch_object_ids,
            }
            self.job.data = {
                "proxbox_sync": {
                    "params": _serialize_sync_params(**params),
                }
            }
            self.job.save(update_fields=["data"])

            if batch_object_type and batch_object_ids:
                self.logger.info(
                    "Starting batch sync for %s selected %s records",
                    len(batch_object_ids),
                    batch_object_type,
                )
                batch_result = asyncio.run(
                    _run_batch_selected_sync(
                        self,
                        batch_object_type=batch_object_type,
                        batch_object_ids=batch_object_ids,
                    )
                )
                runtime_seconds = round(time.monotonic() - run_started, 3)
                self.job.data = {
                    "proxbox_sync": {
                        "params": params,
                        "runtime_seconds": runtime_seconds,
                        "response": {"batch": batch_result},
                    }
                }
                self.job.save(update_fields=["data"])
                self.logger.info(
                    "Batch sync completed for %s (%s total, %s succeeded, %s failed)",
                    batch_result["batch_object_label"],
                    batch_result["total"],
                    batch_result["succeeded"],
                    batch_result["failed"],
                )
                return

            self.logger.info("Starting Proxbox sync stages: %s", ", ".join(stages))
            if proxmox_endpoint_ids:
                self.logger.info("Proxmox endpoints: %s", proxmox_endpoint_ids)
            if netbox_endpoint_ids:
                self.logger.info("NetBox endpoints: %s", netbox_endpoint_ids)
            if netbox_vm_ids:
                self.logger.info("NetBox virtual machines: %s", netbox_vm_ids)

            base_query: dict[str, str] = {}
            base_query["use_guest_agent_interface_name"] = (
                "true" if _use_guest_agent_interface_name_setting() else "false"
            )
            base_query["fetch_max_concurrency"] = str(
                _proxbox_fetch_max_concurrency_setting()
            )
            base_query["ignore_ipv6_link_local_addresses"] = (
                "true" if _ignore_ipv6_link_local_addresses_setting() else "false"
            )
            if proxmox_endpoint_ids:
                base_query["proxmox_endpoint_ids"] = ",".join(proxmox_endpoint_ids)
            if netbox_endpoint_ids:
                base_query["netbox_endpoint_ids"] = ",".join(netbox_endpoint_ids)

            flush_interval = 2.0
            log_throttle = 1.5
            last_flush = time.monotonic()
            last_progress_log = time.monotonic()

            def on_frame(event: str, data: dict[str, object]) -> None:
                nonlocal last_flush, last_progress_log
                if event == "complete":
                    return
                now = time.monotonic()
                line = json.dumps(data, default=str)
                if len(line) > 600:
                    line = line[:600] + "…"
                if event == "error" or now - last_progress_log >= log_throttle:
                    self.logger.info("[proxbox-stream] {}: {}".format(event, line))
                    last_progress_log = now
                if now - last_flush >= flush_interval:
                    self.job.save(update_fields=["log_entries"])
                    last_flush = now

            stages_out: list[dict[str, object]] = []
            for st in stages:
                query_params = dict(base_query)
                if st == SyncTypeChoices.VIRTUAL_MACHINES_BACKUPS:
                    query_params["delete_nonexistent_backup"] = True
                if st == SyncTypeChoices.VIRTUAL_MACHINES_SNAPSHOTS:
                    query_params["delete_nonexistent_snapshot"] = True

                target_vm_ids = [
                    str(x) for x in list(params.get("netbox_vm_ids") or []) if str(x)
                ]
                if target_vm_ids:
                    query_params["netbox_vm_ids"] = ",".join(target_vm_ids)

                stage_paths = _sync_stream_paths_for_stage(st, target_vm_ids)
                for stream_path in stage_paths:
                    self.logger.info("Starting stage: %s (%s)", st, stream_path)
                    payload, status = run_sync_stream(
                        stream_path,
                        query_params=query_params or None,
                        on_frame=on_frame,
                    )
                    self.job.save(update_fields=["log_entries"])
                    if status >= 400:
                        detail = payload.get("detail", "Backend returned an error.")
                        self.logger.error(
                            "Stage %s failed (HTTP %s): %s", st, status, detail
                        )
                        raise RuntimeError(detail)
                    self.logger.info("Stage completed: %s (HTTP %s)", st, status)
                    stages_out.append({"sync_type": st, "payload": payload})

            runtime_seconds = round(time.monotonic() - run_started, 3)
            self.job.data = {
                "proxbox_sync": {
                    "params": params,
                    "runtime_seconds": runtime_seconds,
                    "response": {"stages": stages_out},
                }
            }
            self.job.save(update_fields=["data"])
            self.logger.info(
                "All sync stages completed (%s), runtime %.3fs",
                len(stages_out),
                runtime_seconds,
            )
        finally:
            _release_rq_sync_ownership(self.job)


def is_proxbox_sync_job(job: object) -> bool:
    """True if this core Job row is a Proxbox sync (including user-defined job names)."""
    data = getattr(job, "data", None)
    if isinstance(data, dict) and "proxbox_sync" in data:
        return True
    qn = getattr(job, "queue_name", None) or ""
    if qn == LEGACY_PROXBOX_RQ_QUEUE:
        return True
    default_label = getattr(ProxboxSyncJob.Meta, "name", "Proxbox Sync")
    return not qn and getattr(job, "name", None) == default_label
