"""Streaming SSE endpoint for job progress and logs."""

from __future__ import annotations

import json
import logging
import time
from typing import Generator

from django.http import Http404, HttpRequest, StreamingHttpResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

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
            is_proxbox_sync_job,
            proxbox_sync_params_from_job,
        )
        from netbox_proxbox.services import run_sync_stream
        from netbox_proxbox.jobs import (
            expanded_sync_stages,
            normalize_sync_types,
            _sync_stream_path,
            _VM_SCOPED_PATH_TEMPLATES,
            _use_guest_agent_interface_name_setting,
            _proxbox_fetch_max_concurrency_setting,
            SyncTypeChoices,
        )

        if not is_proxbox_sync_job(job):
            yield from self._emit_error("Not a Proxbox sync job")
            return

        params = proxbox_sync_params_from_job(job)
        sync_types = params.get("sync_types", [SyncTypeChoices.ALL])
        proxmox_endpoint_ids = params.get("proxmox_endpoint_ids", [])
        netbox_endpoint_ids = params.get("netbox_endpoint_ids", [])
        netbox_vm_ids = params.get("netbox_vm_ids", [])

        stages = expanded_sync_stages(sync_types)

        yield from self._emit_step(
            "job", "started", f"Proxbox sync started for {len(stages)} stages"
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
        if proxmox_endpoint_ids:
            base_query["proxmox_endpoint_ids"] = ",".join(proxmox_endpoint_ids)
        if netbox_endpoint_ids:
            base_query["netbox_endpoint_ids"] = ",".join(netbox_endpoint_ids)

        for stage_idx, st in enumerate(stages):
            yield from self._emit_step(
                "progress",
                "started",
                f"Starting stage {stage_idx + 1}/{total_stages}: {st}",
                progress={
                    "current": stage_idx,
                    "total": total_stages,
                    "stage": st,
                },
            )

            query_params = dict(base_query)
            if st == SyncTypeChoices.VIRTUAL_MACHINES_BACKUPS:
                query_params["delete_nonexistent_backup"] = True

            stage_paths: list[str]
            if st in _VM_SCOPED_PATH_TEMPLATES and netbox_vm_ids:
                template = _VM_SCOPED_PATH_TEMPLATES[st]
                stage_paths = [
                    f"{template.format(vm_id=vm_id)}/stream" for vm_id in netbox_vm_ids
                ]
            else:
                stage_paths = [_sync_stream_path(st)]

            stage_ok = True
            for stream_path in stage_paths:
                payload, status = run_sync_stream(
                    stream_path,
                    query_params=query_params or None,
                    on_frame=self._make_frame_callback(job),
                )

                if status >= 400:
                    detail = payload.get("detail", "Backend returned an error.")
                    yield from self._emit_error(
                        f"Stage {st} failed (HTTP {status}): {detail}"
                    )
                    stage_ok = False
                    break

            if not stage_ok:
                break

            completed_stages += 1
            progress_percent = (
                int((completed_stages / total_stages) * 100) if total_stages > 0 else 0
            )
            yield from self._emit_step(
                "progress",
                "completed",
                f"Stage {st} completed",
                progress={
                    "current": completed_stages,
                    "total": total_stages,
                    "stage": st,
                    "percent": progress_percent,
                },
            )

        if completed_stages == total_stages:
            yield from self._emit_step(
                "job", "completed", f"All {total_stages} stages completed"
            )
            yield self._emit_complete(
                True, f"All {total_stages} stages completed successfully"
            )
        else:
            yield from self._emit_error(
                f"Sync incomplete: {completed_stages}/{total_stages} stages"
            )
            yield self._emit_complete(
                False, f"Sync incomplete: {completed_stages}/{total_stages} stages"
            )

    def _make_frame_callback(self, job: JobModel):
        last_flush = [time.monotonic()]

        def on_frame(event: str, data: dict) -> None:
            now = time.monotonic()
            if now - last_flush[0] >= 2.0:
                job.save(update_fields=["log_entries"])
                last_flush[0] = now

        return on_frame

    def _emit_step(
        self,
        step: str,
        status: str,
        message: str,
        progress: dict | None = None,
    ) -> Generator[str, None, None]:
        payload: dict = {
            "step": step,
            "status": status,
            "message": message,
        }
        if progress:
            payload["progress"] = progress

        yield f"event: step\n"
        yield f"data: {json.dumps(payload)}\n\n"

    def _emit_error(self, message: str) -> Generator[str, None, None]:
        yield f"event: error\n"
        yield f"data: {json.dumps({'step': 'job', 'status': 'failed', 'message': message})}\n\n"

    def _emit_complete(self, ok: bool, message: str) -> str:
        return (
            f"event: complete\ndata: {json.dumps({'ok': ok, 'message': message})}\n\n"
        )
