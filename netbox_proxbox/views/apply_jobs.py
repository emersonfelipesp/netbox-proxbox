"""List, detail, and cancel views for Proxmox apply dry-run jobs."""

from __future__ import annotations

from django.contrib import messages
from django.http import HttpRequest, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views import View
from netbox.views import generic
from utilities.permissions import get_permission_for_model
from utilities.views import (
    ContentTypePermissionRequiredMixin,
    TokenConditionalLoginRequiredMixin,
)

from netbox_proxbox.models import ProxmoxApplyJob
from netbox_proxbox.tables.apply_jobs import ProxmoxApplyJobTable

try:
    from netbox.jobs import Job as JobModel
except ImportError:  # pragma: no cover - NetBox test stubs may omit Job
    JobModel = None

__all__ = (
    "ProxmoxApplyJobCancelView",
    "ProxmoxApplyJobListView",
    "ProxmoxApplyJobView",
)


class _ApplyJobViewPermissionMixin(ContentTypePermissionRequiredMixin):
    def get_required_permission(self) -> str:
        return get_permission_for_model(ProxmoxApplyJob, "view")


class ProxmoxApplyJobListView(
    TokenConditionalLoginRequiredMixin,
    _ApplyJobViewPermissionMixin,
    generic.ObjectListView,
):
    """Global list of NetBox→Proxmox intent apply dry-run records."""

    queryset = ProxmoxApplyJob.objects.select_related("user")
    table = ProxmoxApplyJobTable
    template_name = "netbox_proxbox/applyjob_list.html"
    actions = {
        "export": {"view"},
    }


class ProxmoxApplyJobView(
    TokenConditionalLoginRequiredMixin,
    _ApplyJobViewPermissionMixin,
    generic.ObjectView,
):
    """Detail view for one intent apply dry-run record."""

    queryset = ProxmoxApplyJob.objects.select_related("user")
    template_name = "netbox_proxbox/applyjob_detail.html"

    def get_extra_context(
        self, request: HttpRequest, instance: ProxmoxApplyJob
    ) -> dict[str, object]:
        """Expose the matching core Job SSE URL when the RQ row can be found."""
        del request
        if JobModel is None:
            return {"apply_job_sse_url": ""}
        try:
            core_job = (
                JobModel.objects.filter(
                    data__proxbox_apply__run_uuid=str(instance.run_uuid)
                )
                .order_by("-pk")
                .first()
            )
        except Exception:  # pragma: no cover - defensive for JSON lookup support
            core_job = None
        if core_job is None:
            return {"apply_job_sse_url": ""}
        return {
            "apply_job_sse_url": reverse(
                "plugins:netbox_proxbox:job_stream",
                args=[core_job.pk],
            )
        }


class ProxmoxApplyJobCancelView(
    TokenConditionalLoginRequiredMixin,
    ContentTypePermissionRequiredMixin,
    View,
):
    """POST: mark a queued or running intent dry-run as cancelled."""

    http_method_names = ["post"]

    def get_required_permission(self) -> str:
        return get_permission_for_model(ProxmoxApplyJob, "delete")

    def post(self, request: HttpRequest, pk: int | str) -> HttpResponseRedirect:
        apply_job = get_object_or_404(
            ProxmoxApplyJob.objects.restrict(request.user, "view"),
            pk=pk,
        )
        if apply_job.state not in (
            ProxmoxApplyJob.State.queued,
            ProxmoxApplyJob.State.running,
        ):
            messages.warning(
                request,
                _("Only queued or running apply jobs can be cancelled."),
            )
            return HttpResponseRedirect(apply_job.get_absolute_url())

        apply_job.state = ProxmoxApplyJob.State.failed
        apply_job.finished_at = timezone.now()
        results = dict(apply_job.per_vm_results or {})
        results["_cancelled"] = {
            "status": "cancelled",
            "message": "Cancelled by user.",
        }
        apply_job.per_vm_results = results
        apply_job.save(update_fields=["state", "finished_at", "per_vm_results"])
        messages.success(request, _("Apply job has been cancelled."))
        return HttpResponseRedirect(apply_job.get_absolute_url())
