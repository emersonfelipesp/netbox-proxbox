"""Cancel a Proxbox Sync core Job (RQ task + NetBox row)."""

from __future__ import annotations

import logging

from core.choices import JobStatusChoices
from core.models import Job
from core.utils import stop_rq_job
from django.contrib import messages
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext as _
from django.views import View
from django_rq import get_queue
from rq.exceptions import InvalidJobOperation
from rq.job import Job as RQJob
from rq.job import JobStatus as RQJobStatus

from netbox_proxbox.jobs import PROXBOX_SYNC_QUEUE_NAME, is_proxbox_sync_job
from utilities.permissions import get_permission_for_model
from utilities.views import (
    ContentTypePermissionRequiredMixin,
    TokenConditionalLoginRequiredMixin,
    register_model_view,
)

logger = logging.getLogger(__name__)

__all__ = ("ProxboxJobCancelView", "cancel_rq_job_for_netbox_job")


def cancel_rq_job_for_netbox_job(netbox_job: Job) -> bool:
    """Best-effort cancel or stop the RQ job linked to ``netbox_job``.

    Compatibility notes:
    - Prefer NetBox's ``stop_rq_job`` helper so queue/backend differences stay
      encapsulated within NetBox (important for django-rq 4.x compatibility).
    - Fall back to direct queue inspection/cancel for queued/scheduled jobs,
      where a lightweight dequeue operation is preferable to force-stop semantics.

    Returns True if RQ state changed, else False.
    """
    queue_name = (netbox_job.queue_name or "").strip() or PROXBOX_SYNC_QUEUE_NAME
    jid = str(netbox_job.job_id)

    # First attempt a NetBox-native stop path. This is the most stable API
    # surface across NetBox + django-rq integration updates.
    try:
        stopped_jobs = stop_rq_job(jid)
        ok = (
            len(stopped_jobs) == 1
            if isinstance(stopped_jobs, (list, tuple))
            else bool(stopped_jobs)
        )
        if ok:
            logger.info("Stopped RQ job %s via core.utils.stop_rq_job", jid)
            return True
    except Http404:
        logger.info("No RQ job %s found via core.utils.stop_rq_job", jid)
    except Exception as exc:  # pragma: no cover - defensive compatibility fallback
        logger.warning("core.utils.stop_rq_job failed for %s: %s", jid, exc)

    # Fallback path for queued/deferred jobs if direct queue metadata is available.
    queue = get_queue(queue_name)
    rq_job: RQJob | None = queue.fetch_job(jid)

    if rq_job is not None:
        status = rq_job.get_status()
        if status in (
            RQJobStatus.QUEUED,
            RQJobStatus.DEFERRED,
            RQJobStatus.SCHEDULED,
        ):
            try:
                rq_job.cancel()
                logger.info("Cancelled queued RQ job %s on queue %s", jid, queue_name)
                return True
            except InvalidJobOperation as exc:
                logger.warning("RQ cancel failed for %s: %s", jid, exc)
                return False
        if status == RQJobStatus.STARTED:
            try:
                stopped_jobs = stop_rq_job(jid)
                ok = (
                    len(stopped_jobs) == 1
                    if isinstance(stopped_jobs, (list, tuple))
                    else bool(stopped_jobs)
                )
                if ok:
                    logger.info("Sent stop for RQ job %s", jid)
                return ok
            except Http404:
                logger.info("stop_rq_job: RQ job %s not found (may have finished)", jid)
                return False
        logger.info("RQ job %s in state %s; nothing to cancel", jid, status)
        return False

    logger.info("No RQ job %s in queue %s after fallback lookup", jid, queue_name)
    return False


@register_model_view(Job, "proxbox_cancel", path="proxbox-cancel")
class ProxboxJobCancelView(
    TokenConditionalLoginRequiredMixin,
    ContentTypePermissionRequiredMixin,
    View,
):
    """POST: stop/cancel the RQ worker job and mark the NetBox Job as failed."""

    http_method_names = ["post"]

    def get_required_permission(self):
        """Align with deleting a core Job (destructive operational action)."""
        return get_permission_for_model(Job, "delete")

    def post(self, request, pk):
        job = get_object_or_404(Job.objects.restrict(request.user, "view"), pk=pk)
        if not is_proxbox_sync_job(job):
            messages.error(
                request,
                _("This action only applies to Proxbox Sync jobs."),
            )
            return HttpResponseRedirect(job.get_absolute_url())

        if job.status not in JobStatusChoices.ENQUEUED_STATE_CHOICES:
            messages.warning(
                request,
                _("Only pending, scheduled, or running jobs can be cancelled."),
            )
            return HttpResponseRedirect(job.get_absolute_url())

        cancel_rq_job_for_netbox_job(job)

        job.refresh_from_db()
        if job.status not in JobStatusChoices.TERMINAL_STATE_CHOICES:
            job.terminate(
                status=JobStatusChoices.STATUS_FAILED,
                error=str(_("Cancelled by user.")),
            )
            messages.success(request, _("Job has been cancelled."))
        else:
            messages.info(
                request,
                _("Job was already finished; no changes were made."),
            )

        return HttpResponseRedirect(job.get_absolute_url())
