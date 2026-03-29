"""View for scheduling a ProxBox sync job."""

from django.contrib import messages
from django.shortcuts import redirect, render
from django.views import View

from netbox_proxbox.forms.schedule_sync import ScheduleSyncForm
from netbox_proxbox.jobs import ProxboxSyncJob
from netbox_proxbox.views.proxbox_access import permission_add_sync_process
from utilities.views import (
    ContentTypePermissionRequiredMixin,
    TokenConditionalLoginRequiredMixin,
)

__all__ = ("ScheduleSyncView",)


_QUEUE_NAME = "netbox_proxbox.sync"


class ScheduleSyncView(
    TokenConditionalLoginRequiredMixin,
    ContentTypePermissionRequiredMixin,
    View,
):
    def get_required_permission(self):
        return permission_add_sync_process()

    template_name = "netbox_proxbox/schedule_sync.html"

    def get(self, request):
        initial = {}
        sync_type = request.GET.get("sync_type")
        if sync_type:
            initial["sync_type"] = sync_type

        return render(
            request, self.template_name, {"form": ScheduleSyncForm(initial=initial)}
        )

    def post(self, request):
        form = ScheduleSyncForm(request.POST)
        if form.is_valid():
            sync_type = form.cleaned_data["sync_type"]
            schedule_at = form.cleaned_data.get("schedule_at")
            interval = form.cleaned_data.get("interval")
            proxmox_endpoint_ids = form.cleaned_data.get("proxmox_endpoint_ids", [])
            netbox_endpoint_ids = form.cleaned_data.get("netbox_endpoint_ids", [])

            ProxboxSyncJob.enqueue(
                instance=None,
                user=request.user,
                schedule_at=schedule_at,
                interval=interval,
                queue_name=_QUEUE_NAME,
                sync_type=sync_type,
                proxmox_endpoint_ids=proxmox_endpoint_ids,
                netbox_endpoint_ids=netbox_endpoint_ids,
            )

            interval_value = form.cleaned_data.get("interval_value")
            interval_unit = form.cleaned_data.get("interval_unit")

            endpoint_desc = ""
            if proxmox_endpoint_ids:
                endpoint_desc += (
                    f" Proxmox endpoints: {len(proxmox_endpoint_ids)} selected."
                )
            if netbox_endpoint_ids:
                endpoint_desc += (
                    f" NetBox endpoints: {len(netbox_endpoint_ids)} selected."
                )

            if schedule_at:
                interval_desc = ""
                if interval_value and interval_unit:
                    interval_desc = f" Repeats every {interval_value} {interval_unit}."
                messages.success(
                    request,
                    f"Sync job scheduled for {schedule_at.strftime('%Y-%m-%d %H:%M %Z')}.{interval_desc}{endpoint_desc}",
                )
            else:
                messages.success(
                    request, f"Sync job queued for immediate execution.{endpoint_desc}"
                )

            return redirect("core:job_list")

        return render(request, self.template_name, {"form": form})
