"""Individual sync for ProxmoxCluster."""

from django.contrib import messages
from django.http import HttpRequest
from django.http import HttpResponseRedirect
from django.utils.translation import gettext_lazy as _
from django.views import View
from utilities.views import (
    ContentTypePermissionRequiredMixin,
    TokenConditionalLoginRequiredMixin,
    register_model_view,
)

from netbox_proxbox.models import ProxmoxCluster
from netbox_proxbox.services.individual_sync import sync_individual_with_dependencies
from netbox_proxbox.views.proxbox_access import permission_enqueue_proxbox_sync


@register_model_view(ProxmoxCluster, "proxbox_sync_now", path="proxbox-sync-now")
class ProxmoxClusterSyncNowView(
    TokenConditionalLoginRequiredMixin,
    ContentTypePermissionRequiredMixin,
    View,
):
    """POST: sync a single ProxmoxCluster from proxbox-api."""

    http_method_names = ["post"]

    def get_required_permission(self) -> str:
        return permission_enqueue_proxbox_sync()

    def post(self, request: HttpRequest, pk: int | str) -> HttpResponseRedirect:
        cluster = ProxmoxCluster.objects.get(pk=pk)
        cluster_name = cluster.name

        response, status, dependencies = sync_individual_with_dependencies(
            "sync/individual/cluster",
            {"cluster_name": cluster_name},
        )

        if status == 200:
            action = response.get("action", "synced")
            messages.success(
                request,
                _(f"Cluster '{cluster_name}' {action} successfully.")
                + (
                    f" ({len(dependencies)} dependencies synced)"
                    if dependencies
                    else ""
                ),
            )
        elif status == 422:
            messages.error(request, _("Invalid parameters for cluster sync."))
        elif status == 503:
            messages.error(
                request, _("Proxbox backend is unavailable for cluster sync.")
            )
        else:
            error = response.get("error", "Unknown error")
            messages.error(request, _(f"Failed to sync cluster: {error}"))

        return HttpResponseRedirect(cluster.get_absolute_url())
