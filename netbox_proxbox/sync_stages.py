"""Stage execution: batch sync, base/stage query params, and multi-stage orchestration."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable
from typing import TYPE_CHECKING

from netbox_proxbox.choices import SyncTypeChoices
from netbox_proxbox.sync_types import (
    _format_seconds,
    _extract_backend_error_text,
    _format_stage_sync_error,
    _sync_stream_paths_for_stage,
    expanded_sync_stages,
    normalize_sync_types,
)
from netbox_proxbox.sync_params import (
    _normalize_batch_object_ids,
    _resolve_vm_batch_params,
    _resolve_vm_backup_batch_params,
    _resolve_vm_snapshot_batch_params,
    _resolve_storage_batch_params,
    _resolve_task_history_batch_params,
    _proxbox_fetch_max_concurrency_setting,
    _use_guest_agent_interface_name_setting,
    _ignore_ipv6_link_local_addresses_setting,
    _serialize_sync_params,
)
from netbox_proxbox.sync_ownership import (
    _claim_rq_sync_ownership,
    _release_rq_sync_ownership,
)

if TYPE_CHECKING:
    from netbox_proxbox.jobs import ProxboxSyncJob

_HEARTBEAT_SECONDS = 20.0
_STAGE_RETRY_MAX = 2
_STAGE_RETRY_DELAY = 8.0


async def _run_batch_selected_sync(
    self: "ProxboxSyncJob",
    *,
    batch_object_type: str,
    batch_object_ids: list[str],
) -> dict[str, object]:
    """Run selected object syncs concurrently with asyncio.gather."""
    from virtualization.models import VirtualMachine

    from netbox_proxbox.models import (
        ProxmoxStorage,
        VMBackup,
        VMSnapshot,
        VMTaskHistory,
    )
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


def _build_base_query_params(
    proxmox_endpoint_ids: list[str] | None,
    netbox_endpoint_ids: list[str] | None,
) -> dict[str, str]:
    """Build base query parameters for sync stages."""
    base_query: dict[str, str] = {}
    base_query["use_guest_agent_interface_name"] = (
        "true" if _use_guest_agent_interface_name_setting() else "false"
    )
    base_query["fetch_max_concurrency"] = str(_proxbox_fetch_max_concurrency_setting())
    base_query["ignore_ipv6_link_local_addresses"] = (
        "true" if _ignore_ipv6_link_local_addresses_setting() else "false"
    )
    if proxmox_endpoint_ids:
        base_query["proxmox_endpoint_ids"] = ",".join(proxmox_endpoint_ids)
    if netbox_endpoint_ids:
        base_query["netbox_endpoint_ids"] = ",".join(netbox_endpoint_ids)
    return base_query


def _build_stage_query_params(
    base_query: dict[str, str],
    sync_type: str,
    target_vm_ids: list[str],
) -> dict[str, str]:
    """Build query parameters for a specific sync stage."""
    query_params = dict(base_query)
    if sync_type == SyncTypeChoices.VIRTUAL_MACHINES_BACKUPS:
        query_params["delete_nonexistent_backup"] = True
    if sync_type == SyncTypeChoices.VIRTUAL_MACHINES_SNAPSHOTS:
        query_params["delete_nonexistent_snapshot"] = True
    if target_vm_ids:
        query_params["netbox_vm_ids"] = ",".join(target_vm_ids)
    return query_params


def _execute_stage_sync(
    job: "ProxboxSyncJob",
    sync_type: str,
    stream_path: str,
    query_params: dict[str, str] | None,
    on_frame: Callable[[str, dict[str, object]], None],
    endpoint_id: int | None = None,
) -> tuple[dict[str, object], float]:
    """Execute a single stage sync and return payload."""
    from netbox_proxbox.services import run_sync_stream

    job.logger.info(f"Starting stage: {sync_type} ({stream_path})")
    stage_started = time.monotonic()
    last_heartbeat = stage_started

    def _heartbeat() -> None:
        nonlocal last_heartbeat
        now = time.monotonic()
        if now - last_heartbeat < _HEARTBEAT_SECONDS:
            return
        elapsed = _format_seconds(now - stage_started)
        job.logger.info(
            f"Stage '{sync_type}' still running on '{stream_path}' (elapsed {elapsed})"
        )
        last_heartbeat = now

    def _on_frame_with_heartbeat(
        event: str,
        data: dict[str, object],
        forward: Callable[[str, dict[str, object]], None],
    ) -> None:
        forward(event, data)
        _heartbeat()

    last_payload: dict[str, object] = {}
    last_status: int = 0
    for _attempt in range(_STAGE_RETRY_MAX + 1):
        last_payload, last_status = run_sync_stream(
            stream_path,
            query_params=query_params,
            on_frame=lambda e, d: _on_frame_with_heartbeat(e, d, on_frame),
            endpoint_id=endpoint_id,
        )
        elapsed = _format_seconds(time.monotonic() - stage_started)
        job.job.save(update_fields=["log_entries"])

        if last_status < 400:
            stage_runtime = round(time.monotonic() - stage_started, 3)
            job.logger.info(
                f"Stage completed: {sync_type} ({stream_path}) HTTP {last_status} in {elapsed}"
            )
            return last_payload, stage_runtime

        if last_status >= 500 and _attempt < _STAGE_RETRY_MAX:
            retry_detail = _extract_backend_error_text(last_payload) or str(
                last_payload
            )
            job.logger.warning(
                f"Stage {sync_type} failed (HTTP {last_status}): {retry_detail} "
                f"-- retrying in {_STAGE_RETRY_DELAY:.0f}s "
                f"(attempt {_attempt + 1}/{_STAGE_RETRY_MAX})"
            )
            job.job.save(update_fields=["log_entries"])
            time.sleep(_STAGE_RETRY_DELAY)
            continue

        # 4xx (not retryable) or all retries exhausted
        break

    detail = _extract_backend_error_text(last_payload) or str(last_payload)
    user_detail = _format_stage_sync_error(
        sync_type=sync_type,
        status=last_status,
        payload=last_payload,
    )
    job.logger.error(f"Stage {sync_type} failed (HTTP {last_status}): {detail}")
    raise RuntimeError(user_detail)


def _run_all_stages_sync(
    job: "ProxboxSyncJob",
    stages: list[str],
    params: dict[str, object],
    run_started: float,
) -> list[dict[str, object]]:
    """Run all sync stages in order and return stage results."""
    from netbox_proxbox.services import run_sync_stream

    base_query = _build_base_query_params(
        params.get("proxmox_endpoint_ids"),
        params.get("netbox_endpoint_ids"),
    )

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
            job.logger.info("[proxbox-stream] {}: {}".format(event, line))
            last_progress_log = now
        if now - last_flush >= flush_interval:
            job.job.save(update_fields=["log_entries"])
            last_flush = now

    stages_out: list[dict[str, object]] = []

    target_vm_ids = [str(x) for x in list(params.get("netbox_vm_ids") or []) if str(x)]
    fastapi_endpoint_id = params.get("fastapi_endpoint_id")

    for st in stages:
        query_params = _build_stage_query_params(base_query, st, target_vm_ids)
        stage_paths = _sync_stream_paths_for_stage(st, target_vm_ids)

        for stream_path in stage_paths:
            payload, stage_runtime = _execute_stage_sync(
                job, st, stream_path, query_params, on_frame, fastapi_endpoint_id
            )
            stages_out.append(
                {"sync_type": st, "payload": payload, "runtime_seconds": stage_runtime}
            )

    return stages_out
