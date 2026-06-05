"""Individual sync for VirtualMachine using proxbox-api individual sync endpoint."""

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
from virtualization.models import VirtualMachine

from netbox_proxbox.models import ProxmoxCluster
from netbox_proxbox.utils import resolve_vm_type
from netbox_proxbox.services.branch_lifecycle import get_active_branch_schema_id
from netbox_proxbox.services.individual_sync import sync_individual_with_dependencies
from netbox_proxbox.services.tenant_assignment import (
    maybe_assign_tenant_from_regex,
    maybe_assign_tenant_from_tags,
)
from netbox_proxbox.views.proxbox_access import permission_enqueue_proxbox_sync
from netbox_proxbox.views.sync_now import _handle_sync_response


@register_model_view(VirtualMachine, "proxbox_sync_now", path="proxbox-sync-now")
class VirtualMachineSyncNowView(
    TokenConditionalLoginRequiredMixin,
    ContentTypePermissionRequiredMixin,
    View,
):
    """POST: sync a single VirtualMachine from proxbox-api using individual sync."""

    http_method_names = ["post"]

    def get_required_permission(self) -> str:
        """Return required permission."""
        return permission_enqueue_proxbox_sync()

    def post(self, request: HttpRequest, pk: int | str) -> HttpResponseRedirect:
        """Handle post."""
        vm = get_object_or_404(
            VirtualMachine.objects.restrict(request.user, "view"), pk=pk
        )

        vmid = vm.custom_field_data.get("proxmox_vm_id") or vm.custom_field_data.get(
            "cf_proxmox_vm_id"
        )
        vm_type = resolve_vm_type(vm)
        proxmox_cluster = ProxmoxCluster.objects.filter(
            netbox_cluster=vm.cluster
        ).first()
        cluster_name = (
            proxmox_cluster.name
            if proxmox_cluster
            else (vm.cluster.name if vm.cluster else "")
        )

        node = ""
        if hasattr(vm, "device") and vm.device:
            node = vm.device.name
        else:
            node = vm.custom_field_data.get("proxmox_node") or vm.custom_field_data.get(
                "cf_proxmox_node", ""
            )

        if not vmid:
            messages.error(request, _("Virtual machine does not have a Proxmox VM ID."))
            return HttpResponseRedirect(vm.get_absolute_url())

        if not cluster_name:
            messages.error(
                request,
                _("Virtual machine is not linked to a Proxmox cluster."),
            )
            return HttpResponseRedirect(vm.get_absolute_url())

        response, status, dependencies = sync_individual_with_dependencies(
            "sync/individual/vm",
            {
                "cluster_name": cluster_name,
                "node": node,
                "type": vm_type,
                "vmid": vmid,
            },
            netbox_branch_schema_id=get_active_branch_schema_id(),
        )

        if 200 <= status < 300:
            vm.refresh_from_db()
            endpoint_id = proxmox_cluster.endpoint_id if proxmox_cluster else None
            maybe_assign_tenant_from_regex(vm, endpoint_id=endpoint_id)
            maybe_assign_tenant_from_tags(vm, endpoint_id=endpoint_id)

        return _handle_sync_response(
            request,
            response,
            status,
            dependencies,
            f"Virtual machine '{vm.name}'",
            vm.get_absolute_url(),
        )
