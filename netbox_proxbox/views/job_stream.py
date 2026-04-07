"""Streaming SSE endpoint for job progress and logs."""

from __future__ import annotations

import json
import logging
import queue
import re
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


_STREAM_LOG_RE = re.compile(r"^\[proxbox-stream\]\s+(\S+):\s*(.+)$")


def _decode_stream_log_entry(entry: object) -> tuple[str, dict[str, object]] | None:
    """Decode persisted ``[proxbox-stream] ...`` log entries into SSE frames."""
    if not isinstance(entry, dict):
        return None
    raw = entry.get("message")
    if not isinstance(raw, str):
        return None
    match = _STREAM_LOG_RE.match(raw.strip())
    if not match:
        return None
    event = match.group(1).strip() or "message"
    payload_raw = match.group(2).strip()
    if not payload_raw:
        return event, {"message": ""}
    try:
        payload = json.loads(payload_raw)
    except json.JSONDecodeError:
        return event, {"raw": payload_raw}
    if isinstance(payload, dict):
        return event, payload
    return event, {"raw": payload}


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
        """Handle get."""
        job = JobModel.objects.filter(pk=pk).first()
        if not job:
            raise Http404("Job not found")

        return StreamingHttpResponse(
            self._stream_job_events(job),
            content_type="text/event-stream",
        )

    def _stream_job_events(self, job: JobModel) -> Generator[str, None, None]:
        from netbox_proxbox.jobs import is_proxbox_sync_job

        event_queue: queue.Queue[object] = queue.Queue()
        queue_sentinel = object()

        def emit(event: str, payload: dict[str, object]) -> None:
            event_queue.put(self._serialize_sse(event, payload))

        def emit_error(message: str) -> None:
            emit(
                "error",
                {"step": "job", "status": "failed", "message": message},
            )

        def emit_complete(ok: bool, message: str, *, status: str | None = None) -> None:
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
                                "message": f"Job is still {queued_status}; waiting for a worker.",
                            },
                        )
                        emit_complete(
                            False,
                            f"Job is still {queued_status}; waiting for a worker.",
                            status="waiting",
                        )
                        return

                sync_owner = _get_sync_ownership(job)
                emit(
                    "step",
                    {
                        "step": "job",
                        "status": "started",
                        "message": (
                            "Observing Proxbox sync job progress"
                            if not sync_owner
                            else f"Observing Proxbox sync handled by {sync_owner}"
                        ),
                    },
                )

                last_status = status
                emitted_terminal = False
                seen_log_entries = 0

                while True:
                    job.refresh_from_db()
                    current_status = getattr(job, "status", None)

                    if current_status != last_status:
                        emit(
                            "step",
                            {
                                "step": "job",
                                "status": current_status,
                                "message": f"Job status changed to {current_status}",
                            },
                        )
                        last_status = current_status

                    log_entries = getattr(job, "log_entries", None)
                    if isinstance(log_entries, list):
                        new_entries = log_entries[seen_log_entries:]
                        for entry in new_entries:
                            decoded = _decode_stream_log_entry(entry)
                            if decoded is not None:
                                event_name, payload = decoded
                                if event_name != "complete":
                                    emit(event_name, payload)
                                continue
                            if isinstance(entry, dict):
                                msg = entry.get("message")
                                if isinstance(msg, str) and msg.strip():
                                    emit(
                                        "message",
                                        {
                                            "step": "job",
                                            "status": "progress",
                                            "message": msg,
                                        },
                                    )
                        seen_log_entries = len(log_entries)

                    if current_status in JobStatusChoices.TERMINAL_STATE_CHOICES:
                        ok = current_status == JobStatusChoices.STATUS_COMPLETED
                        emit_complete(ok, f"Job finished with status {current_status}")
                        emitted_terminal = True
                        break

                    time.sleep(SYNC_WAIT_POLL_INTERVAL)

                if not emitted_terminal:
                    emit_complete(False, "Job stream ended unexpectedly")
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

    def _serialize_sse(self, event: str, payload: dict[str, object]) -> str:
        return f"event: {event}\ndata: {json.dumps(payload)}\n\n"
