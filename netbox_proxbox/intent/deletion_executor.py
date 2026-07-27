"""Executor RQ job for approved Proxmox deletion requests."""

from __future__ import annotations

import logging
import uuid
from typing import Any

import requests
from django.utils import timezone
from netbox.constants import RQ_QUEUE_DEFAULT
from netbox.jobs import JobRunner

try:
    from netbox.jobs import Job
except ImportError:  # pragma: no cover - test stubs expose only JobRunner
    Job = Any  # type: ignore[misc,assignment]

from netbox_proxbox.models import DeletionRequest, ProxboxPluginSettings
from netbox_proxbox.services.backend_context import get_fastapi_request_context

DELETION_EXECUTOR_JOB_TIMEOUT = 3600

__all__ = ("DELETION_EXECUTOR_JOB_TIMEOUT", "DeletionExecutorJob")

logger = logging.getLogger(__name__)


def _self_approval_allowed() -> bool:
    settings_obj = ProxboxPluginSettings.get_solo()
    return bool(settings_obj.intent_apply_authorization_self_approve_allowed)


def _trim_reason(reason: object) -> str:
    text = str(reason or "").strip()
    return text[:255] if text else "Deletion executor failed."


def _response_body(response: requests.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


def _stamp_executor_run_uuid(
    deletion_request: DeletionRequest,
    body: dict[str, Any],
) -> bool:
    value = body.get("executor_run_uuid") or body.get("run_uuid")
    if not value:
        return False
    try:
        deletion_request.executor_run_uuid = uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        logger.warning("proxbox-api returned invalid executor run UUID: %r", value)
        return False
    return True


class DeletionExecutorJob(JobRunner):
    """Dispatch one approved DeletionRequest to proxbox-api for execution."""

    class Meta:
        name = "Proxmox Deletion Executor"

    @classmethod
    def enqueue(
        cls,
        *,
        deletion_request_id: int,
        user: Any,
        job_timeout: int = DELETION_EXECUTOR_JOB_TIMEOUT,
    ) -> Job:
        """Enqueue execution for an approved DeletionRequest."""
        deletion_request = DeletionRequest.objects.get(pk=deletion_request_id)
        label = deletion_request.name or f"DeletionRequest #{deletion_request.pk}"
        job = super().enqueue(
            instance=None,
            user=user,
            queue_name=RQ_QUEUE_DEFAULT,
            job_timeout=job_timeout,
            name=f"Execute {label}",
            deletion_request_id=deletion_request_id,
        )
        job.data = {
            "proxbox_deletion_request": {
                "deletion_request_id": deletion_request_id,
            }
        }
        job.save(update_fields=["data"])
        logger.info(
            "Queued DeletionRequest %s executor as NetBox Job %s.",
            deletion_request_id,
            getattr(job, "pk", None),
        )
        return job

    def run(self, *args: object, **kwargs: object) -> None:
        """Execute an approved DeletionRequest through proxbox-api."""
        deletion_request_id = kwargs.get("deletion_request_id")
        if deletion_request_id is None and args:
            deletion_request_id = args[0]

        dr = None
        try:
            dr = DeletionRequest.objects.get(pk=deletion_request_id)

            if dr.state != DeletionRequest.State.APPROVED:
                logger.warning(
                    "DeletionRequest %s is in state %s, not APPROVED; aborting executor.",
                    deletion_request_id,
                    dr.state,
                )
                return

            if (
                dr.authorizer_id is not None
                and dr.authorizer_id == dr.requested_by_id
                and not _self_approval_allowed()
            ):
                dr.state = DeletionRequest.State.FAILED
                dr.reject_reason = "self-approval blocked"
                dr.save(update_fields=["state", "reject_reason"])
                return

            dr.state = DeletionRequest.State.EXECUTING
            dr.executed_at = timezone.now()
            dr.save(update_fields=["state", "executed_at"])

            context = get_fastapi_request_context()
            if context is None:
                raise RuntimeError(
                    "No FastAPIEndpoint is configured; cannot execute deletion request."
                )
            if not context.http_url:
                raise RuntimeError("FastAPIEndpoint has no resolvable http_url.")

            actor = getattr(dr, "authorizer", None)
            actor_username = getattr(actor, "username", None)
            url = (
                f"{context.http_url.rstrip('/')}/intent/deletion-requests/"
                f"{dr.pk}/execute"
            )
            headers = dict(context.headers or {})
            headers.setdefault("Content-Type", "application/json")
            headers["X-Proxbox-Actor"] = actor_username or ""

            response = requests.post(
                url,
                json={"vmid": dr.vmid, "node": dr.node, "kind": dr.kind},
                headers=headers,
                timeout=DELETION_EXECUTOR_JOB_TIMEOUT,
                verify=bool(context.verify_ssl),
                allow_redirects=False,
            )
            body = _response_body(response)
            uuid_changed = _stamp_executor_run_uuid(dr, body)

            update_fields = ["state"]
            if uuid_changed:
                update_fields.append("executor_run_uuid")

            if 200 <= response.status_code < 300:
                dr.state = DeletionRequest.State.SUCCEEDED
            else:
                detail = (
                    body.get("detail")
                    or body.get("message")
                    or f"proxbox-api returned HTTP {response.status_code}"
                )
                dr.state = DeletionRequest.State.FAILED
                dr.reject_reason = _trim_reason(detail)
                update_fields.append("reject_reason")

            dr.save(update_fields=update_fields)
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "DeletionRequest %s executor failed: %s",
                deletion_request_id,
                exc,
            )
            if dr is not None:
                dr.state = DeletionRequest.State.FAILED
                dr.reject_reason = _trim_reason(exc)
                dr.save(update_fields=["state", "reject_reason"])
