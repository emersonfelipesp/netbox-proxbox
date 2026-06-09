"""Queue an immediate Proxbox sync from a ProxmoxEndpoint detail page."""

from __future__ import annotations

from django.contrib import messages
from django.http import HttpRequest, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from utilities.views import register_model_view

from netbox_proxbox.choices import SyncTypeChoices
from netbox_proxbox.jobs import PROXBOX_SYNC_QUEUE_NAME, ProxboxSyncJob
from netbox_proxbox.models import ProxmoxEndpoint
from netbox_proxbox.views.sync_helpers import (
    _ProxboxSyncViewBase,
    build_job_name,
    notify_sync_enqueued,
    notify_sync_error,
)

__all__ = ("ProxmoxEndpointSyncNowView",)


@register_model_view(ProxmoxEndpoint, "sync_now", path="sync-now")
class ProxmoxEndpointSyncNowView(_ProxboxSyncViewBase):
    """POST: enqueue a full Proxbox sync scoped to one ProxmoxEndpoint."""

    http_method_names = ["post"]

    def post(self, request: HttpRequest, pk: int | str) -> HttpResponseRedirect:
        """Queue an immediate full sync for the visible endpoint."""
        endpoint = get_object_or_404(
            ProxmoxEndpoint.objects.restrict(request.user, "view"),
            pk=pk,
        )
        redirect_url = endpoint.get_absolute_url()

        if not endpoint.enabled:
            messages.warning(
                request,
                _("Disabled Proxmox endpoints cannot run sync jobs."),
            )
            return HttpResponseRedirect(redirect_url)

        try:
            job = ProxboxSyncJob.enqueue(
                instance=None,
                user=request.user,
                queue_name=PROXBOX_SYNC_QUEUE_NAME,
                name=build_job_name(
                    str(_("Proxmox endpoint {}")).format(endpoint.name)
                ),
                sync_types=[SyncTypeChoices.ALL],
                proxmox_endpoint_ids=[str(endpoint.pk)],
            )
            notify_sync_enqueued(
                request,
                job,
                _(
                    "A Proxbox sync job for this endpoint has been queued. "
                    "Open the job to follow progress."
                ),
            )
        except Exception as exc:  # noqa: BLE001 - surface enqueue failures to operators
            notify_sync_error(request, exc)

        return HttpResponseRedirect(redirect_url)
