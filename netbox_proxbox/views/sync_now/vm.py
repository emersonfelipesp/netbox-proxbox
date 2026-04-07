"""Individual sync for VirtualMachine using proxbox-api individual sync endpoint."""

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
from virtualization.models import VirtualMachine

from netbox_proxbox.models import ProxmoxCluster
from netbox_proxbox.services.individual_sync import sync_individual_with_dependencies
from netbox_proxbox.views.proxbox_access import permission_enqueue_proxbox_sync


@register_model_view(VirtualMachine, "proxbox_sync_now", path="proxbox-sync-now")
class VirtualMachineSyncNowView(
    TokenConditionalLoginRequiredMixin,
    ContentTypePermissionRequiredMixin,
    View,
):
    """POST: sync a single VirtualMachine from proxbox-api using individual sync."""

    http_method_names = ["post"]

    def get_required_permission(self) -> str:
        return permission_enqueue_proxbox_sync()

    def post(self, request: HttpRequest, pk: int | str) -> HttpResponseRedirect:
        vm = VirtualMachine.objects.get(pk=pk)

        vmid = vm.custom_field_data.get("proxmox_vm_id") or vm.custom_field_data.get(
            "cf_proxmox_vm_id"
        )
        vm_type = vm.custom_field_data.get(
            "proxmox_vm_type"
        ) or vm.custom_field_data.get("cf_proxmox_vm_type", "qemu")
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
        )

        if status == 200:
            action = response.get("action", "synced")
            messages.success(
                request,
                _(f"Virtual machine '{vm.name}' {action} successfully.")
                + (
                    f" ({len(dependencies)} dependencies synced)"
                    if dependencies
                    else ""
                ),
            )
        elif status == 422:
            messages.error(request, _("Invalid parameters for virtual machine sync."))
        elif status == 503:
            messages.error(
                request, _("Proxbox backend is unavailable for virtual machine sync.")
            )
        else:
            error = response.get("error", "Unknown error")
            messages.error(request, _(f"Failed to sync virtual machine: {error}"))

        return HttpResponseRedirect(vm.get_absolute_url())
