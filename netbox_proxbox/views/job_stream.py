"""Streaming SSE endpoint for job progress and logs."""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
from typing import Generator

from django.http import Http404, HttpRequest, StreamingHttpResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from netbox.jobs import Job as JobModel

logger = logging.getLogger(__name__)


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

        def emit_complete(ok: bool, message: str) -> None:
            emit("complete", {"ok": ok, "message": message})

        def worker() -> None:
            try:
                if not is_proxbox_sync_job(job):
                    emit_error("Not a Proxbox sync job")
                    emit_complete(False, "Not a Proxbox sync job")
                    return

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
