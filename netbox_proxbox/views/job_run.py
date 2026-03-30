"""Re-queue a Proxbox Sync job from the NetBox core Job detail page."""

from __future__ import annotations

from core.choices import JobStatusChoices
from core.models import Job
from django.contrib import messages
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext as _
from django.views import View

from netbox_proxbox.jobs import (
    PROXBOX_SYNC_QUEUE_NAME,
    ProxboxSyncJob,
    is_proxbox_sync_job,
    proxbox_sync_params_from_job,
)
from netbox_proxbox.views.proxbox_access import permission_add_sync_process
from utilities.views import (
    ContentTypePermissionRequiredMixin,
    TokenConditionalLoginRequiredMixin,
    register_model_view,
)

__all__ = ("ProxboxJobRunNowView",)


@register_model_view(Job, "proxbox_run", path="proxbox-run")
class ProxboxJobRunNowView(
    TokenConditionalLoginRequiredMixin,
    ContentTypePermissionRequiredMixin,
    View,
):
    """POST: enqueue a new immediate Proxbox sync using the same parameters as this job."""

    http_method_names = ["post"]

    def get_required_permission(self):
        """Require ``add`` on ``SyncProcess`` (same gate as the schedule form)."""
        return permission_add_sync_process()

    def post(self, request, pk):
        """Clone sync parameters onto a new queued job and redirect to its detail page."""
        job = get_object_or_404(Job.objects.restrict(request.user, "view"), pk=pk)
        if not is_proxbox_sync_job(job):
            messages.error(
                request,
                _("This action only applies to Proxbox Sync jobs."),
            )
            return HttpResponseRedirect(job.get_absolute_url())
        if job.status not in JobStatusChoices.TERMINAL_STATE_CHOICES:
            messages.warning(
                request,
                _(
                    "Run now is only available after the job has finished, failed, or been "
                    "cancelled."
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
        messages.success(
            request,
            _("A new Proxbox sync job has been queued."),
        )
        return HttpResponseRedirect(new_job.get_absolute_url())
