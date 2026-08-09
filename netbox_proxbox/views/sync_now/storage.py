"""Individual sync for ProxmoxStorage."""

from django.contrib import messages
from django.http import HttpRequest
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from django.views import View
from utilities.views import (
    ContentTypePermissionRequiredMixin,
    TokenConditionalLoginRequiredMixin,
    register_model_view,
)

from netbox_proxbox.models import ProxmoxStorage
from netbox_proxbox.services.branch_lifecycle import get_active_branch_schema_id
from netbox_proxbox.services.individual_sync import sync_individual_with_dependencies
from netbox_proxbox.views.proxbox_access import permission_enqueue_proxbox_sync
from netbox_proxbox.views.sync_now import _handle_sync_response
from netbox_proxbox.views.sync_now.endpoint_scope import (
    resolve_target_proxmox_endpoint_scope,
)


@register_model_view(ProxmoxStorage, "proxbox_sync_now", path="proxbox-sync-now")
class ProxmoxStorageSyncNowView(
    TokenConditionalLoginRequiredMixin,
    ContentTypePermissionRequiredMixin,
    View,
):
    """POST: sync a single ProxmoxStorage from proxbox-api."""

    http_method_names = ["post"]

    def get_required_permission(self) -> str:
        """Return required permission."""
        return permission_enqueue_proxbox_sync()

    def post(self, request: HttpRequest, pk: int | str) -> HttpResponseRedirect:
        """Handle post."""
        storage = get_object_or_404(
            ProxmoxStorage.objects.restrict(request.user, "view"), pk=pk
        )
        storage_name = storage.name
        cluster_name = storage.cluster.name if storage.cluster else ""

        if not cluster_name:
            messages.error(request, _("Storage is not linked to a Proxmox cluster."))
            return HttpResponseRedirect(storage.get_absolute_url())

        scope_kwargs, owner_cluster_name, scope_error = (
            resolve_target_proxmox_endpoint_scope(storage)
        )
        if scope_kwargs is None:
            messages.error(
                request,
                scope_error or _("Storage ownership could not be resolved for sync."),
            )
            return HttpResponseRedirect(storage.get_absolute_url())
        if owner_cluster_name:
            cluster_name = owner_cluster_name

        response, status, dependencies = sync_individual_with_dependencies(
            "sync/individual/storage",
            {"cluster_name": cluster_name, "storage_name": storage_name},
            netbox_branch_schema_id=get_active_branch_schema_id(),
            **scope_kwargs,
        )

        return _handle_sync_response(
            request,
            response,
            status,
            dependencies,
            f"Storage '{storage_name}'",
            storage.get_absolute_url(),
        )
