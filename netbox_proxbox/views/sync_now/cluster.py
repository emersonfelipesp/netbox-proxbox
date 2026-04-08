"""Individual sync for ProxmoxCluster."""

from django.http import HttpRequest
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.views import View
from utilities.views import (
    ContentTypePermissionRequiredMixin,
    TokenConditionalLoginRequiredMixin,
    register_model_view,
)

from netbox_proxbox.models import ProxmoxCluster
from netbox_proxbox.services.individual_sync import sync_individual_with_dependencies
from netbox_proxbox.views.proxbox_access import permission_enqueue_proxbox_sync
from netbox_proxbox.views.sync_now import _handle_sync_response


@register_model_view(ProxmoxCluster, "proxbox_sync_now", path="proxbox-sync-now")
class ProxmoxClusterSyncNowView(
    TokenConditionalLoginRequiredMixin,
    ContentTypePermissionRequiredMixin,
    View,
):
    """POST: sync a single ProxmoxCluster from proxbox-api."""

    http_method_names = ["post"]

    def get_required_permission(self) -> str:
        """Return required permission."""
        return permission_enqueue_proxbox_sync()

    def post(self, request: HttpRequest, pk: int | str) -> HttpResponseRedirect:
        """Handle post."""
        cluster = get_object_or_404(
            ProxmoxCluster.objects.restrict(request.user, "view"), pk=pk
        )
        cluster_name = cluster.name

        response, status, dependencies = sync_individual_with_dependencies(
            "sync/individual/cluster",
            {"cluster_name": cluster_name},
        )

        return _handle_sync_response(
            request,
            response,
            status,
            dependencies,
            f"Cluster '{cluster_name}'",
            cluster.get_absolute_url(),
        )
