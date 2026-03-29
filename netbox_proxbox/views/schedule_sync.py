"""View for scheduling a ProxBox sync job."""

from django.contrib import messages
from django.shortcuts import redirect, render
from django.views import View

from netbox_proxbox.forms.schedule_sync import ScheduleSyncForm
from netbox_proxbox.jobs import ProxboxSyncJob

__all__ = ("ScheduleSyncView",)

_QUEUE_NAME = "netbox_proxbox.sync"


class ScheduleSyncView(View):
    template_name = "netbox_proxbox/schedule_sync.html"

    def get(self, request):
        return render(request, self.template_name, {"form": ScheduleSyncForm()})

    def post(self, request):
        form = ScheduleSyncForm(request.POST)
        if form.is_valid():
            sync_type = form.cleaned_data["sync_type"]
            schedule_at = form.cleaned_data.get("schedule_at")
            interval = form.cleaned_data.get("interval")

            ProxboxSyncJob.enqueue(
                instance=None,
                user=request.user,
                schedule_at=schedule_at,
                interval=interval,
                queue_name=_QUEUE_NAME,
                sync_type=sync_type,
            )

            if schedule_at:
                messages.success(
                    request,
                    f"Sync job scheduled for {schedule_at.strftime('%Y-%m-%d %H:%M %Z')}."
                    + (f" Repeats every {interval} minute(s)." if interval else ""),
                )
            else:
                messages.success(request, "Sync job queued for immediate execution.")

            return redirect("core:job_list")

        return render(request, self.template_name, {"form": form})
