"""REST endpoint to cancel a Proxbox Sync core Job.

JSON mirror of the UI ``proxbox-cancel`` action (``views/job_cancel.py``) so a
stuck/zombie Proxbox sync job can be cleared through the nms-backend
``/netbox/netbox-proxbox/plugin/*`` proxy (e.g. ``nms virt cancel-job``) without
the NetBox UI. It reuses the exact cancel helper the UI uses — no duplicated
RQ/termination logic — and gates on the same ``core.delete_job`` permission.
"""

from __future__ import annotations

from core.choices import JobStatusChoices
from core.models import Job
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from netbox_proxbox.jobs import is_proxbox_sync_job
from netbox_proxbox.views.job_cancel import cancel_rq_job_for_netbox_job

__all__ = ("ProxboxJobCancelAPIView",)


class _ProxboxJobCancelPermission(BasePermission):
    """Require the same core Job delete permission the UI cancel action uses."""

    def has_permission(self, request: Request, view: object) -> bool:
        """Allow only authenticated users holding ``core.delete_job``."""
        user = getattr(request, "user", None)
        return bool(
            user
            and getattr(user, "is_authenticated", False)
            and user.has_perm("core.delete_job")
        )


class ProxboxJobCancelAPIView(APIView):
    """POST: stop/cancel the RQ job for a Proxbox Sync Job and mark it failed."""

    http_method_names = ["post", "options"]
    permission_classes = [_ProxboxJobCancelPermission]

    def post(self, request: Request, pk: int) -> Response:
        """Cancel a Proxbox Sync job, returning the resulting job state as JSON."""
        job = get_object_or_404(Job.objects.restrict(request.user, "view"), pk=pk)

        if not is_proxbox_sync_job(job):
            return Response(
                {
                    "ok": False,
                    "detail": "This action only applies to Proxbox Sync jobs.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # An already-terminal job (completed/errored/failed) is a safe no-op —
        # this covers a job someone else just cancelled and a duplicate request.
        if job.status in JobStatusChoices.TERMINAL_STATE_CHOICES:
            return Response(
                {
                    "ok": True,
                    "job_id": job.pk,
                    "status": job.status,
                    "detail": "Job was already finished; no changes were made.",
                }
            )

        # Best-effort stop/cancel of the linked RQ job (a dead-worker zombie has
        # none, which is fine), then mark the NetBox Job row failed so a stale
        # "running" row is cleared even when the RQ side is already gone.
        cancel_rq_job_for_netbox_job(job)
        job.refresh_from_db()
        if job.status not in JobStatusChoices.TERMINAL_STATE_CHOICES:
            job.terminate(
                status=JobStatusChoices.STATUS_FAILED,
                error="Cancelled via API.",
            )
            job.refresh_from_db()

        return Response(
            {
                "ok": True,
                "job_id": job.pk,
                "status": job.status,
                "detail": "Job has been cancelled.",
            }
        )
