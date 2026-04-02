"""Individual sync for ProxmoxNode."""

from django.contrib import messages
from django.http import HttpResponseRedirect
from django.utils.translation import gettext_lazy as _
from django.views import View
from utilities.views import (
    ContentTypePermissionRequiredMixin,
    TokenConditionalLoginRequiredMixin,
    register_model_view,
)

from netbox_proxbox.models import ProxmoxNode
from netbox_proxbox.services.individual_sync import sync_individual_with_dependencies
from netbox_proxbox.views.proxbox_access import permission_enqueue_proxbox_sync


@register_model_view(ProxmoxNode, "proxbox_sync_now", path="proxbox-sync-now")
class ProxmoxNodeSyncNowView(
    TokenConditionalLoginRequiredMixin,
    ContentTypePermissionRequiredMixin,
    View,
):
    """POST: sync a single ProxmoxNode from proxbox-api."""

    http_method_names = ["post"]

    def get_required_permission(self):
        return permission_enqueue_proxbox_sync()

    def post(self, request, pk):
        node = ProxmoxNode.objects.get(pk=pk)
        node_name = node.name

        cluster_name = ""
        if node.proxmox_cluster:
            cluster_name = node.proxmox_cluster.name
        elif node.netbox_device and node.netbox_device.cluster:
            cluster_name = node.netbox_device.cluster.name

        if not cluster_name:
            messages.error(request, _("Node is not linked to a Proxmox cluster."))
            return HttpResponseRedirect(node.get_absolute_url())

        response, status, dependencies = sync_individual_with_dependencies(
            "sync/individual/node",
            {"cluster_name": cluster_name, "node_name": node_name},
        )

        if status == 200:
            action = response.get("action", "synced")
            messages.success(
                request,
                _(f"Node '{node_name}' {action} successfully.")
                + (
                    f" ({len(dependencies)} dependencies synced)"
                    if dependencies
                    else ""
                ),
            )
        elif status == 422:
            messages.error(request, _("Invalid parameters for node sync."))
        elif status == 503:
            messages.error(request, _("Proxbox backend is unavailable for node sync."))
        else:
            error = response.get("error", "Unknown error")
            messages.error(request, _(f"Failed to sync node: {error}"))

        return HttpResponseRedirect(node.get_absolute_url())
