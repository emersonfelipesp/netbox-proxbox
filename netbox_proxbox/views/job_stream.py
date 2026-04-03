"""Streaming SSE endpoint for job progress and logs."""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
from typing import Generator

from core.choices import JobStatusChoices
from django.http import Http404, HttpRequest, StreamingHttpResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from netbox.jobs import Job as JobModel

logger = logging.getLogger(__name__)

SYNC_OWNER_SSE = "sse_stream"
SYNC_OWNER_RQ = "rq_job"

SYNC_WAIT_TIMEOUT = 60
SYNC_WAIT_POLL_INTERVAL = 0.5


def _claim_sync_ownership(job: JobModel, owner: str) -> bool:
    """Atomically claim sync ownership on a job. Returns True if claimed, False if already taken."""
    import datetime as dt

    data = getattr(job, "data", None) or {}
    if isinstance(data, str):
        try:
            data = json.loads(data) if data else {}
        except (json.JSONDecodeError, TypeError):
            data = {}
    proxbox_sync = data.get("proxbox_sync", {})
    current_owner = proxbox_sync.get("sync_owner")
    if current_owner and current_owner != owner:
        return False
    proxbox_sync["sync_owner"] = owner
    proxbox_sync["sync_owner_claimed_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    data["proxbox_sync"] = proxbox_sync
    job.data = data
    job.save(update_fields=["data"])
    return True


def _get_sync_ownership(job: JobModel) -> str | None:
    """Return the current sync owner for a job, or None if not claimed."""
    data = getattr(job, "data", None)
    if isinstance(data, str):
        try:
            data = json.loads(data) if data else {}
        except (json.JSONDecodeError, TypeError):
            data = {}
    return data.get("proxbox_sync", {}).get("sync_owner")


def _release_sync_ownership(job: JobModel, owner: str) -> None:
    """Release sync ownership if we are the owner."""
    data = getattr(job, "data", None)
    if isinstance(data, str):
        try:
            data = json.loads(data) if data else {}
        except (json.JSONDecodeError, TypeError):
            data = {}
    proxbox_sync = data.get("proxbox_sync", {})
    if proxbox_sync.get("sync_owner") == owner:
        del proxbox_sync["sync_owner"]
        if proxbox_sync.get("sync_owner_claimed_at"):
            del proxbox_sync["sync_owner_claimed_at"]
        data["proxbox_sync"] = proxbox_sync
        job.data = data
        job.save(update_fields=["data"])


def _wait_for_job_status(
    job: JobModel,
    target_status: str,
    timeout: float = SYNC_WAIT_TIMEOUT,
    poll_interval: float = SYNC_WAIT_POLL_INTERVAL,
) -> str:
    """Wait for job to reach target status, returning the final status."""
    start = time.monotonic()
    job.refresh_from_db()
    current = getattr(job, "status", None)
    while current != target_status:
        elapsed = time.monotonic() - start
        if elapsed >= timeout:
            logger.warning(
                "Timed out waiting for job %s to reach status %s (current: %s, elapsed: %.1fs)",
                getattr(job, "pk", "?"),
                target_status,
                current,
                elapsed,
            )
            return current
        time.sleep(poll_interval)
        job.refresh_from_db()
        current = getattr(job, "status", None)
    return current


@method_decorator(csrf_exempt, name="dispatch")
class JobStreamSSEView(View):
    """Stream SSE for job status, progress, and live log entries."""

    http_method_names = ["get"]

    def get(self, request: HttpRequest, pk: int) -> StreamingHttpResponse:
        job = JobModel.objects.filter(pk=pk).first()
        if not job:
            raise Http404("Job not found")

        return StreamingHttpResponse(
            self._stream_job_events(job),
            content_type="text/event-stream",
        )

    def _stream_job_events(self, job: JobModel) -> Generator[str, None, None]:
        from netbox_proxbox.jobs import (
            _VM_SCOPED_PATH_TEMPLATES,
            SyncTypeChoices,
            _ignore_ipv6_link_local_addresses_setting,
            _proxbox_fetch_max_concurrency_setting,
            _sync_stream_path,
            _use_guest_agent_interface_name_setting,
            expanded_sync_stages,
            is_proxbox_sync_job,
            proxbox_sync_params_from_job,
        )
        from netbox_proxbox.services import run_sync_stream

        event_queue: queue.Queue[object] = queue.Queue()
        queue_sentinel = object()

        def emit(event: str, payload: dict[str, object]) -> None:
            event_queue.put(self._serialize_sse(event, payload))

        def emit_error(message: str) -> None:
            emit(
                "error",
                {"step": "job", "status": "failed", "message": message},
            )

        def emit_complete(
            ok: bool, message: str, *, status: str | None = None
        ) -> None:
            payload: dict[str, object] = {"ok": ok, "message": message}
            if status is not None:
                payload["status"] = status
            emit("complete", payload)

        def worker() -> None:
            try:
                if not is_proxbox_sync_job(job):
                    emit_error("Not a Proxbox sync job")
                    emit_complete(False, "Not a Proxbox sync job")
                    return

                job.refresh_from_db()
                status = getattr(job, "status", None)

                if status in JobStatusChoices.TERMINAL_STATE_CHOICES:
                    emit(
                        "step",
                        {
                            "step": "job",
                            "status": status,
                            "message": f"Job is already {status}",
                        },
                    )
                    emit_complete(
                        status == JobStatusChoices.STATUS_COMPLETED,
                        f"Job is already {status}",
                    )
                    return

                if status in (
                    JobStatusChoices.STATUS_PENDING,
                    JobStatusChoices.STATUS_SCHEDULED,
                ):
                    emit(
                        "step",
                        {
                            "step": "job",
                            "status": "waiting",
                            "message": f"Job is {status}, waiting for worker to start...",
                        },
                    )
                    status = _wait_for_job_status(job, JobStatusChoices.STATUS_RUNNING)
                    if status != JobStatusChoices.STATUS_RUNNING:
                        queued_status = str(status or "unknown")
                        emit(
                            "step",
                            {
                                "step": "job",
                                "status": "waiting",
                                "message": (
                                    f"Job is still {queued_status}; continuing to poll."
                                ),
                            },
                        )
                        emit_complete(
                            False,
                            f"Job is still {queued_status}; continuing to poll.",
                            status="waiting",
                        )
                        return

                if not _claim_sync_ownership(job, SYNC_OWNER_SSE):
                    existing_owner = _get_sync_ownership(job)
                    logger.info(
                        "Job %s sync ownership already claimed by %s, skipping SSE sync",
                        getattr(job, "pk", "?"),
                        existing_owner,
                    )
                    emit(
                        "step",
                        {
                            "step": "job",
                            "status": "running",
                            "message": "Job sync is being handled by another process",
                        },
                    )
                    emit_complete(False, "Job sync is being handled by another process")
                    return

                emit(
                    "step",
                    {
                        "step": "job",
                        "status": "started",
                        "message": "SSE stream has claimed sync ownership",
                    },
                )

                params = proxbox_sync_params_from_job(job)
                sync_types = params.get("sync_types", [SyncTypeChoices.ALL])
                proxmox_endpoint_ids = params.get("proxmox_endpoint_ids", [])
                netbox_endpoint_ids = params.get("netbox_endpoint_ids", [])
                netbox_vm_ids = params.get("netbox_vm_ids", [])

                stages = expanded_sync_stages(sync_types)

                emit(
                    "step",
                    {
                        "step": "job",
                        "status": "started",
                        "message": f"Proxbox sync started for {len(stages)} stages",
                    },
                )

                total_stages = len(stages)
                completed_stages = 0

                base_query: dict = {}
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

                frame_callback = self._make_frame_callback(job)

                for stage_idx, st in enumerate(stages):
                    emit(
                        "step",
                        {
                            "step": "progress",
                            "status": "started",
                            "message": f"Starting stage {stage_idx + 1}/{total_stages}: {st}",
                            "progress": {
                                "current": stage_idx,
                                "total": total_stages,
                                "stage": st,
                            },
                        },
                    )

                    query_params = dict(base_query)
                    if st == SyncTypeChoices.VIRTUAL_MACHINES_BACKUPS:
                        query_params["delete_nonexistent_backup"] = True

                    stage_paths: list[str]
                    if st in _VM_SCOPED_PATH_TEMPLATES and netbox_vm_ids:
                        template = _VM_SCOPED_PATH_TEMPLATES[st]
                        stage_paths = [
                            f"{template.format(vm_id=vm_id)}/stream"
                            for vm_id in netbox_vm_ids
                        ]
                    else:
                        stage_paths = [_sync_stream_path(st)]

                    stage_ok = True
                    for stream_path in stage_paths:

                        def on_frame(event: str, data: dict[str, object]) -> None:
                            frame_callback(event, data)
                            if event == "complete":
                                return
                            emit(event, data)

                        payload, status = run_sync_stream(
                            stream_path,
                            query_params=query_params or None,
                            on_frame=on_frame,
                        )

                        if status >= 400:
                            detail = payload.get("detail", "Backend returned an error.")
                            emit_error(f"Stage {st} failed (HTTP {status}): {detail}")
                            stage_ok = False
                            break

                    if not stage_ok:
                        break

                    completed_stages += 1
                    progress_percent = (
                        int((completed_stages / total_stages) * 100)
                        if total_stages > 0
                        else 0
                    )
                    emit(
                        "step",
                        {
                            "step": "progress",
                            "status": "completed",
                            "message": f"Stage {st} completed",
                            "progress": {
                                "current": completed_stages,
                                "total": total_stages,
                                "stage": st,
                                "percent": progress_percent,
                            },
                        },
                    )

                if completed_stages == total_stages:
                    emit(
                        "step",
                        {
                            "step": "job",
                            "status": "completed",
                            "message": f"All {total_stages} stages completed",
                        },
                    )
                    emit_complete(
                        True,
                        f"All {total_stages} stages completed successfully",
                    )
                else:
                    emit_error(
                        f"Sync incomplete: {completed_stages}/{total_stages} stages"
                    )
                    emit_complete(
                        False,
                        f"Sync incomplete: {completed_stages}/{total_stages} stages",
                    )
            except Exception as exc:  # pragma: no cover - defensive stream guard
                logger.exception(
                    "Unexpected error streaming job %s", getattr(job, "pk", "?")
                )
                emit_error(f"Job stream failed unexpectedly: {exc}")
                emit_complete(False, "Job stream failed unexpectedly.")
            finally:
                _release_sync_ownership(job, SYNC_OWNER_SSE)
                event_queue.put(queue_sentinel)

        stream_thread = threading.Thread(target=worker, daemon=True)
        stream_thread.start()

        try:
            while True:
                item = event_queue.get()
                if item is queue_sentinel:
                    break
                yield str(item)
        finally:
            stream_thread.join(timeout=1)

    def _make_frame_callback(self, job: JobModel):
        last_flush = [time.monotonic()]

        def on_frame(event: str, data: dict) -> None:
            now = time.monotonic()
            if now - last_flush[0] >= 2.0:
                job.save(update_fields=["log_entries"])
                last_flush[0] = now

        return on_frame

    def _serialize_sse(self, event: str, payload: dict[str, object]) -> str:
        return f"event: {event}\ndata: {json.dumps(payload)}\n\n"
