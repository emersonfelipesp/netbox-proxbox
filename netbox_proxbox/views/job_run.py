"""Re-queue or immediately run a Proxbox Sync job from the NetBox core Job detail page."""

from __future__ import annotations

from core.choices import JobStatusChoices
from core.models import Job
from django.contrib import messages
from django.http import HttpRequest, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext as _
from django.views import View

from netbox_proxbox.jobs import (
    PROXBOX_SYNC_QUEUE_NAME,
    ProxboxSyncJob,
    is_proxbox_sync_job,
    proxbox_sync_params_from_job,
)
from netbox_proxbox.views.proxbox_access import permission_enqueue_proxbox_sync
from utilities.views import (
    ContentTypePermissionRequiredMixin,
    TokenConditionalLoginRequiredMixin,
    register_model_view,
)

__all__ = ("ProxboxJobRunNowView",)


_ALLOWED_RUN_NOW_STATUSES = (
    *JobStatusChoices.TERMINAL_STATE_CHOICES,
    JobStatusChoices.STATUS_SCHEDULED,
)


@register_model_view(Job, "proxbox_run", path="proxbox-run")
class ProxboxJobRunNowView(
    TokenConditionalLoginRequiredMixin,
    ContentTypePermissionRequiredMixin,
    View,
):
    """POST: enqueue a new immediate Proxbox sync using the same parameters as this job.

    Allowed for terminal jobs (re-run after completion/failure) and for scheduled jobs
    (run immediately without cancelling the original — it will still execute on schedule).
    """

    http_method_names = ["post"]

    def get_required_permission(self) -> str:
        """Require ``add`` on core ``Job`` (same gate as the schedule form)."""
        return permission_enqueue_proxbox_sync()

    def post(self, request: HttpRequest, pk: int | str) -> HttpResponseRedirect:
        """Clone sync parameters onto a new queued job and redirect to its detail page."""
        job = get_object_or_404(Job.objects.restrict(request.user, "view"), pk=pk)
        if not is_proxbox_sync_job(job):
            messages.error(
                request,
                _("This action only applies to Proxbox Sync jobs."),
            )
            return HttpResponseRedirect(job.get_absolute_url())
        if job.status not in _ALLOWED_RUN_NOW_STATUSES:
            messages.warning(
                request,
                _(
                    "Run now is only available for finished, failed, cancelled, or scheduled jobs."
                ),
            )
            return HttpResponseRedirect(job.get_absolute_url())

        enqueue_kwargs = proxbox_sync_params_from_job(job)
        new_job = ProxboxSyncJob.enqueue(
            instance=None,
            user=request.user,
            queue_name=PROXBOX_SYNC_QUEUE_NAME,
            name=job.name,
            **enqueue_kwargs,
        )
        if job.status == JobStatusChoices.STATUS_SCHEDULED:
            messages.success(
                request,
                _(
                    "A new Proxbox sync job has been queued to run immediately. "
                    "The original scheduled job is unchanged."
                ),
            )
        else:
            messages.success(
                request,
                _("A new Proxbox sync job has been queued."),
            )
        return HttpResponseRedirect(new_job.get_absolute_url())
