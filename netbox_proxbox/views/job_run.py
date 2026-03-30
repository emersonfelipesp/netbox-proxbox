"""Re-queue a Proxbox Sync job from the NetBox core Job detail page."""

from __future__ import annotations

from core.choices import JobStatusChoices
from core.models import Job
from django.contrib import messages
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext as _
from django.views import View

from netbox_proxbox.jobs import ProxboxSyncJob, proxbox_sync_params_from_job
from netbox_proxbox.views.proxbox_access import permission_add_sync_process
from utilities.views import (
    ContentTypePermissionRequiredMixin,
    TokenConditionalLoginRequiredMixin,
    register_model_view,
)

__all__ = ("ProxboxJobRunNowView",)

_QUEUE_NAME = "netbox_proxbox.sync"


@register_model_view(Job, "proxbox_run", path="proxbox-run")
class ProxboxJobRunNowView(
    TokenConditionalLoginRequiredMixin,
    ContentTypePermissionRequiredMixin,
    View,
):
    """POST: enqueue a new immediate Proxbox sync using the same parameters as this job."""

    http_method_names = ["post"]

    def get_required_permission(self):
        return permission_add_sync_process()

    def post(self, request, pk):
        job = get_object_or_404(Job.objects.restrict(request.user, "view"), pk=pk)
        if job.name != ProxboxSyncJob.name:
            messages.error(
                request,
                _("This action only applies to Proxbox Sync jobs."),
            )
            return HttpResponseRedirect(job.get_absolute_url())
        if job.status in (
            JobStatusChoices.STATUS_PENDING,
            JobStatusChoices.STATUS_RUNNING,
        ):
            messages.warning(
                request,
                _("Cannot run again while this job is pending or still running."),
            )
            return HttpResponseRedirect(job.get_absolute_url())

        enqueue_kwargs = proxbox_sync_params_from_job(job)
        new_job = ProxboxSyncJob.enqueue(
            instance=None,
            user=request.user,
            queue_name=_QUEUE_NAME,
            **enqueue_kwargs,
        )
        messages.success(
            request,
            _("A new Proxbox sync job has been queued."),
        )
        return HttpResponseRedirect(new_job.get_absolute_url())
