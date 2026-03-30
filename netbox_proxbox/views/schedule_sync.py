"""View for scheduling a ProxBox sync job."""

from django.contrib import messages
from django.shortcuts import redirect, render
from django.views import View

from netbox_proxbox.choices import SyncTypeChoices
from netbox_proxbox.forms.schedule_sync import ScheduleSyncForm
from netbox_proxbox.jobs import PROXBOX_SYNC_QUEUE_NAME, ProxboxSyncJob
from netbox_proxbox.views.home_context import build_home_dashboard_context
from netbox_proxbox.views.proxbox_access import permission_add_sync_process
from utilities.views import (
    ContentTypePermissionRequiredMixin,
    TokenConditionalLoginRequiredMixin,
)

__all__ = (
    "QuickScheduleSyncFromHomeView",
    "ScheduleSyncView",
    "enqueue_proxbox_sync_from_valid_form",
    "schedule_sync_success_message",
)


def enqueue_proxbox_sync_from_valid_form(request, form: ScheduleSyncForm) -> None:
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

    def get_required_permission(self):
        """Require ``add`` on ``SyncProcess`` to enqueue jobs."""
        return permission_add_sync_process()

    template_name = "netbox_proxbox/schedule_sync.html"

    def get(self, request):
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

        return render(
            request, self.template_name, {"form": ScheduleSyncForm(initial=initial)}
        )

    def post(self, request):
        """Validate the form, enqueue ``ProxboxSyncJob``, then redirect to the job list."""
        form = ScheduleSyncForm(request.POST)
        if form.is_valid():
            enqueue_proxbox_sync_from_valid_form(request, form)
            messages.success(request, schedule_sync_success_message(form))
            return redirect("core:job_list")

        return render(request, self.template_name, {"form": form})


class QuickScheduleSyncFromHomeView(
    TokenConditionalLoginRequiredMixin,
    ContentTypePermissionRequiredMixin,
    View,
):
    """POST-only: enqueue from the home quick-schedule card; re-render home on errors."""

    def get_required_permission(self):
        """Require ``add`` on ``SyncProcess`` to enqueue jobs."""
        return permission_add_sync_process()

    def get(self, request):
        """Always send users to the plugin home."""
        return redirect("plugins:netbox_proxbox:home")

    def post(self, request):
        """Validate the quick form and enqueue like ``ScheduleSyncView``; stay on home."""
        form = ScheduleSyncForm(request.POST)
        if form.is_valid():
            enqueue_proxbox_sync_from_valid_form(request, form)
            messages.success(request, schedule_sync_success_message(form))
            return redirect("plugins:netbox_proxbox:home")

        context = build_home_dashboard_context(request, quick_schedule_form=form)
        return render(request, "netbox_proxbox/home.html", context)
