"""View for scheduling a ProxBox sync job."""

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views import View

from core.choices import JobStatusChoices
from core.models import Job
from netbox_proxbox.choices import SyncTypeChoices
from netbox_proxbox.forms.schedule_sync import ScheduleSyncForm
from netbox_proxbox.jobs import (
    PROXBOX_SYNC_QUEUE_NAME,
    ProxboxSyncJob,
    is_proxbox_sync_job,
    proxbox_sync_params_from_job,
)
from netbox_proxbox.views.home_context import build_home_dashboard_context
from netbox_proxbox.views.proxbox_access import permission_enqueue_proxbox_sync
from netbox_proxbox.views.schedule_helpers import (
    build_initial_from_job as _build_initial_from_job,
    get_scheduled_jobs_list as _get_scheduled_jobs_list,
)
from utilities.views import (
    ContentTypePermissionRequiredMixin,
    TokenConditionalLoginRequiredMixin,
)

__all__ = (
    "QuickScheduleSyncFromHomeView",
    "ScheduleSyncView",
    "build_initial_from_job",
    "enqueue_proxbox_sync_from_valid_form",
    "get_scheduled_jobs_list",
    "proxbox_sync_params_from_job",
    "schedule_sync_success_message",
)


def build_initial_from_job(request: HttpRequest, edit_job_id: str) -> dict:
    """Compatibility wrapper around the extracted helper.

    Tests and older call sites patch this module-level symbol directly, so keep the
    view module as the stable integration surface even after the helper extraction.
    """
    from netbox_proxbox.models import NetBoxEndpoint, ProxmoxEndpoint

    try:
        job = Job.objects.restrict(request.user, "view").get(pk=edit_job_id)
    except Job.DoesNotExist:
        return {}

    if not is_proxbox_sync_job(job):
        return {}

    params = proxbox_sync_params_from_job(job)
    initial = {
        "job_name": job.name or "",
        "sync_types": params.get("sync_types", []),
    }
    proxmox_endpoint_ids = params.get("proxmox_endpoint_ids", [])
    netbox_endpoint_ids = params.get("netbox_endpoint_ids", [])
    if proxmox_endpoint_ids:
        initial["proxmox_endpoints"] = list(
            ProxmoxEndpoint.objects.filter(pk__in=proxmox_endpoint_ids)
        )
    if netbox_endpoint_ids:
        initial["netbox_endpoints"] = list(
            NetBoxEndpoint.objects.filter(pk__in=netbox_endpoint_ids)
        )
    if job.scheduled:
        initial["schedule_at"] = job.scheduled
    if not job.interval:
        return initial
    interval_minutes = job.interval
    if interval_minutes >= 60 * 24 * 7:
        initial["interval_value"] = interval_minutes // (60 * 24 * 7)
        initial["interval_unit"] = "weeks"
    elif interval_minutes >= 60 * 24:
        initial["interval_value"] = interval_minutes // (60 * 24)
        initial["interval_unit"] = "days"
    elif interval_minutes >= 60:
        initial["interval_value"] = interval_minutes // 60
        initial["interval_unit"] = "hours"
    else:
        initial["interval_value"] = interval_minutes
        initial["interval_unit"] = "minutes"
    return initial


def get_scheduled_jobs_list(request: HttpRequest) -> list[dict]:
    """Compatibility wrapper around the extracted helper."""
    scheduled_jobs: list[dict] = []
    candidates = (
        Job.objects.restrict(request.user, "view")
        .exclude(status=JobStatusChoices.STATUS_COMPLETED)
        .order_by("-created")
    )
    for job in candidates.iterator(chunk_size=64):
        if not is_proxbox_sync_job(job):
            continue
        params = proxbox_sync_params_from_job(job)
        scheduled_jobs.append(
            {
                "id": job.pk,
                "pk": job.pk,
                "name": job.name,
                "sync_types": params.get("sync_types", []),
                "schedule": job.scheduled,
                "interval": job.interval,
                "status": job.status,
            }
        )
    return scheduled_jobs


def _mark_job_canceled(job: Job) -> None:
    """Mark a scheduled Proxbox job as user-cancelled using a valid terminal status."""
    job.status = JobStatusChoices.STATUS_FAILED
    job.error = "Cancelled by user."
    job.completed = timezone.now()
    job.save(update_fields=["status", "error", "completed"])


def enqueue_proxbox_sync_from_valid_form(
    request: HttpRequest, form: ScheduleSyncForm
) -> None:
    """Enqueue ``ProxboxSyncJob`` from a bound, valid ``ScheduleSyncForm``."""
    sync_types = form.cleaned_data["sync_types"]
    schedule_at = form.cleaned_data.get("schedule_at")
    interval = form.cleaned_data.get("interval")
    proxmox_endpoint_ids = form.cleaned_data.get("proxmox_endpoint_ids", [])
    netbox_endpoint_ids = form.cleaned_data.get("netbox_endpoint_ids", [])
    job_name = form.cleaned_data.get("job_name") or ""

    enqueue_kwargs = dict(
        instance=None,
        user=request.user,
        schedule_at=schedule_at,
        interval=interval,
        queue_name=PROXBOX_SYNC_QUEUE_NAME,
        sync_types=sync_types,
        proxmox_endpoint_ids=proxmox_endpoint_ids,
        netbox_endpoint_ids=netbox_endpoint_ids,
    )
    if job_name:
        enqueue_kwargs["name"] = job_name

    ProxboxSyncJob.enqueue(**enqueue_kwargs)


def schedule_sync_success_message(form: ScheduleSyncForm) -> str:
    """Human-readable success line for a valid schedule form (mirrors prior view strings)."""
    schedule_at = form.cleaned_data.get("schedule_at")
    interval_value = form.cleaned_data.get("interval_value")
    interval_unit = form.cleaned_data.get("interval_unit")
    proxmox_endpoint_ids = form.cleaned_data.get("proxmox_endpoint_ids", [])
    netbox_endpoint_ids = form.cleaned_data.get("netbox_endpoint_ids", [])

    endpoint_desc = ""
    if proxmox_endpoint_ids:
        endpoint_desc += f" Proxmox endpoints: {len(proxmox_endpoint_ids)} selected."
    if netbox_endpoint_ids:
        endpoint_desc += f" NetBox endpoints: {len(netbox_endpoint_ids)} selected."

    if schedule_at:
        interval_desc = ""
        if interval_value and interval_unit:
            interval_desc = f" Repeats every {interval_value} {interval_unit}."
        return (
            f"Sync job scheduled for {schedule_at.strftime('%Y-%m-%d %H:%M %Z')}."
            f"{interval_desc}{endpoint_desc}"
        )
    return f"Sync job queued for immediate execution.{endpoint_desc}"


class ScheduleSyncView(
    TokenConditionalLoginRequiredMixin,
    ContentTypePermissionRequiredMixin,
    View,
):
    """Render and process the ProxBox background sync scheduling form."""

    def get_required_permission(self) -> str:
        """Require ``add`` on core ``Job`` to enqueue jobs."""
        return permission_enqueue_proxbox_sync()

    template_name = "netbox_proxbox/schedule_sync.html"

    def get(self, request: HttpRequest) -> HttpResponse:
        """Show the schedule form, optionally pre-selecting ``sync_types`` from query string."""
        initial = {}
        valid_slugs = {c[0] for c in SyncTypeChoices.CHOICES}
        multi = request.GET.getlist("sync_types")
        if multi:
            picked = [x for x in multi if x in valid_slugs]
            if picked:
                initial["sync_types"] = picked
        else:
            single = request.GET.get("sync_type")
            if single and single in valid_slugs:
                initial["sync_types"] = [single]

        edit_job_id = request.GET.get("edit")

        if edit_job_id:
            initial.update(build_initial_from_job(request, edit_job_id))

        scheduled_jobs = get_scheduled_jobs_list(request)

        return render(
            request,
            self.template_name,
            {
                "form": ScheduleSyncForm(initial=initial),
                "scheduled_jobs": scheduled_jobs,
                "edit_job": edit_job_id,
            },
        )

    def post(self, request: HttpRequest) -> HttpResponse:
        """Validate the form, enqueue ``ProxboxSyncJob``, then redirect to the job list."""
        cancel_job_id = request.POST.get("cancel_job")
        if cancel_job_id:
            from django.utils.translation import gettext as _

            try:
                job = Job.objects.restrict(request.user, "view").get(pk=cancel_job_id)
                if (
                    is_proxbox_sync_job(job)
                    and job.status in JobStatusChoices.ENQUEUED_STATE_CHOICES
                ):
                    _mark_job_canceled(job)
                    messages.success(
                        request, _("Scheduled job cancelled successfully.")
                    )
            except Job.DoesNotExist:
                messages.error(request, _("Job not found."))

            return redirect("plugins:netbox_proxbox:schedule_sync")

        edit_job_id = request.POST.get("edit_job_id")
        if edit_job_id:
            try:
                old_job = Job.objects.restrict(request.user, "view").get(pk=edit_job_id)
                if (
                    is_proxbox_sync_job(old_job)
                    and old_job.status in JobStatusChoices.ENQUEUED_STATE_CHOICES
                ):
                    _mark_job_canceled(old_job)
            except Job.DoesNotExist:
                pass

        form = ScheduleSyncForm(request.POST)
        if form.is_valid():
            enqueue_proxbox_sync_from_valid_form(request, form)
            messages.success(request, schedule_sync_success_message(form))
            return redirect("core:job_list")

        return render(
            request,
            self.template_name,
            {"form": form, "scheduled_jobs": [], "edit_job": edit_job_id},
        )


class QuickScheduleSyncFromHomeView(
    TokenConditionalLoginRequiredMixin,
    ContentTypePermissionRequiredMixin,
    View,
):
    """POST-only: enqueue from the home quick-schedule card; re-render home on errors."""

    def get_required_permission(self) -> str:
        """Require ``add`` on core ``Job`` to enqueue jobs."""
        return permission_enqueue_proxbox_sync()

    def get(self, request: HttpRequest) -> HttpResponse:
        """Always send users to the plugin home."""
        return redirect("plugins:netbox_proxbox:home")

    def post(self, request: HttpRequest) -> HttpResponse:
        """Validate the quick form and enqueue like ``ScheduleSyncView``; stay on home."""
        form = ScheduleSyncForm(
            request.POST,
            use_bootstrap_sync_checkboxes=True,
        )
        if form.is_valid():
            enqueue_proxbox_sync_from_valid_form(request, form)
            messages.success(request, schedule_sync_success_message(form))
            return redirect("plugins:netbox_proxbox:home")

        context = build_home_dashboard_context(request, quick_schedule_form=form)
        return render(request, "netbox_proxbox/home.html", context)
