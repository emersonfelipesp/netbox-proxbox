"""Background job for triggering ProxBox sync operations via the FastAPI backend."""

from __future__ import annotations

import json
import time
from typing import Any

from netbox.constants import RQ_QUEUE_DEFAULT
from netbox.jobs import JobRunner

from netbox_proxbox.choices import SyncTypeChoices

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
}

_ALLOWED_SYNC_SLUGS = frozenset(_SYNC_TYPE_PATH) | {SyncTypeChoices.ALL}

_STAGE_ORDER_INDEX = {t: i for i, t in enumerate(_SYNC_STAGE_ORDER)}


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


def proxbox_sync_params_from_job(job: Any) -> dict[str, Any]:
    """Rebuild ProxboxSyncJob.enqueue kwargs from job.data (with safe fallbacks)."""
    data = job.data if isinstance(getattr(job, "data", None), dict) else {}
    block = data.get("proxbox_sync")
    if not isinstance(block, dict):
        block = {}
    params = block.get("params")
    if not isinstance(params, dict):
        return {
            "sync_types": [SyncTypeChoices.ALL],
            "proxmox_endpoint_ids": [],
            "netbox_endpoint_ids": [],
            "netbox_vm_ids": [],
        }
    proxmox = list(params.get("proxmox_endpoint_ids") or [])
    netbox = list(params.get("netbox_endpoint_ids") or [])
    netbox_vms = [str(x) for x in list(params.get("netbox_vm_ids") or []) if str(x)]
    raw_list = params.get("sync_types")
    if isinstance(raw_list, list) and len(raw_list) > 0:
        sync_types = normalize_sync_types([str(x) for x in raw_list])
    else:
        legacy = params.get("sync_type") or SyncTypeChoices.ALL
        sync_types = normalize_sync_types([str(legacy)])
    return {
        "sync_types": sync_types,
        "proxmox_endpoint_ids": proxmox,
        "netbox_endpoint_ids": netbox,
        "netbox_vm_ids": netbox_vms,
    }


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
        if sync_types_kw is not None:
            normalized = normalize_sync_types(list(sync_types_kw))
        elif sync_type_kw is not None:
            normalized = normalize_sync_types([str(sync_type_kw)])
        else:
            normalized = [SyncTypeChoices.ALL]
        kwargs["sync_types"] = normalized

        job = super().enqueue(*args, **kwargs)

        params = {
            "sync_types": normalized,
            "proxmox_endpoint_ids": list(kwargs.get("proxmox_endpoint_ids") or []),
            "netbox_endpoint_ids": list(kwargs.get("netbox_endpoint_ids") or []),
            "netbox_vm_ids": [
                str(x) for x in list(kwargs.get("netbox_vm_ids") or []) if str(x)
            ],
        }
        job.data = {"proxbox_sync": {"params": params}}
        job.save(update_fields=["data"])
        return job

    def run(
        self,
        sync_types: list[str] | None = None,
        sync_type: str | None = None,
        proxmox_endpoint_ids: list[str] | None = None,
        netbox_endpoint_ids: list[str] | None = None,
        netbox_vm_ids: list[str] | None = None,
        **kwargs,
    ):
        """Run one or more proxbox-api SSE streams in dependency order."""
        from netbox_proxbox.services import run_sync_stream

        if sync_types:
            types = normalize_sync_types([str(x) for x in sync_types])
        elif sync_type is not None:
            types = normalize_sync_types([str(sync_type)])
        else:
            types = [SyncTypeChoices.ALL]

        stages = expanded_sync_stages(types)

        params: dict[str, Any] = {
            "sync_types": types,
            "proxmox_endpoint_ids": list(proxmox_endpoint_ids or []),
            "netbox_endpoint_ids": list(netbox_endpoint_ids or []),
            "netbox_vm_ids": [str(x) for x in list(netbox_vm_ids or []) if str(x)],
        }
        self.job.data = {"proxbox_sync": {"params": params}}
        self.job.save(update_fields=["data"])

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
        if proxmox_endpoint_ids:
            base_query["proxmox_endpoint_ids"] = ",".join(proxmox_endpoint_ids)
        if netbox_endpoint_ids:
            base_query["netbox_endpoint_ids"] = ",".join(netbox_endpoint_ids)

        flush_interval = 2.0
        log_throttle = 1.5
        last_flush = time.monotonic()
        last_progress_log = time.monotonic()

        def on_frame(event: str, data: dict[str, Any]) -> None:
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

        run_started = time.monotonic()
        stages_out: list[dict[str, Any]] = []
        for st in stages:
            query_params = dict(base_query)
            if st == SyncTypeChoices.VIRTUAL_MACHINES_BACKUPS:
                query_params["delete_nonexistent_backup"] = True
            target_vm_ids = params.get("netbox_vm_ids", [])
            stage_paths: list[str]
            if st == SyncTypeChoices.VIRTUAL_MACHINES and target_vm_ids:
                stage_paths = [
                    f"virtualization/virtual-machines/{vm_id}/create/stream"
                    for vm_id in target_vm_ids
                ]
            else:
                stage_paths = [_sync_stream_path(st)]

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


def is_proxbox_sync_job(job: Any) -> bool:
    """True if this core Job row is a Proxbox sync (including user-defined job names)."""
    data = getattr(job, "data", None)
    if isinstance(data, dict) and "proxbox_sync" in data:
        return True
    qn = getattr(job, "queue_name", None) or ""
    if qn == LEGACY_PROXBOX_RQ_QUEUE:
        return True
    default_label = getattr(ProxboxSyncJob.Meta, "name", "Proxbox Sync")
    return not qn and getattr(job, "name", None) == default_label
