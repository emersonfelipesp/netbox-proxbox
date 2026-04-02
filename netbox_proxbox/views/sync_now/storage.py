"""Individual sync for ProxmoxStorage."""

from django.contrib import messages
from django.http import HttpResponseRedirect
from django.utils.translation import gettext_lazy as _
from django.views import View
from utilities.views import (
    ContentTypePermissionRequiredMixin,
    TokenConditionalLoginRequiredMixin,
    register_model_view,
)

from netbox_proxbox.models import ProxmoxStorage
from netbox_proxbox.services.individual_sync import sync_individual_with_dependencies
from netbox_proxbox.views.proxbox_access import permission_enqueue_proxbox_sync


@register_model_view(ProxmoxStorage, "proxbox_sync_now", path="proxbox-sync-now")
class ProxmoxStorageSyncNowView(
    TokenConditionalLoginRequiredMixin,
    ContentTypePermissionRequiredMixin,
    View,
):
    """POST: sync a single ProxmoxStorage from proxbox-api."""

    http_method_names = ["post"]

    def get_required_permission(self):
        return permission_enqueue_proxbox_sync()

    def post(self, request, pk):
        storage = ProxmoxStorage.objects.get(pk=pk)
        storage_name = storage.name
        cluster_name = storage.cluster.name if storage.cluster else ""

        response, status, dependencies = sync_individual_with_dependencies(
            "sync/individual/storage",
            {"cluster_name": cluster_name, "storage_name": storage_name},
        )

        if status == 200:
            action = response.get("action", "synced")
            messages.success(
                request,
                _(f"Storage '{storage_name}' {action} successfully.")
                + (
                    f" ({len(dependencies)} dependencies synced)"
                    if dependencies
                    else ""
                ),
            )
        else:
            error = response.get("error", "Unknown error")
            messages.error(request, _(f"Failed to sync storage: {error}"))

        return HttpResponseRedirect(storage.get_absolute_url())
