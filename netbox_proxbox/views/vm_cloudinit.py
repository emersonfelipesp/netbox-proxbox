"""Provide NetBox CRUD and tab views for Proxmox VM cloud-init records (issue #363).

The model is read-only from a NetBox-user perspective: ``ProxmoxVMCloudInitForm``
disables every editable field. Edits flow in only via the plugin DRF endpoint
``/api/plugins/proxbox/vm-cloudinit/`` driven by proxbox-api.
"""

from django.http import HttpRequest
from netbox.views import generic
from utilities.views import ViewTab, register_model_view
from virtualization.models import VirtualMachine

from netbox_proxbox.filtersets import ProxmoxVMCloudInitFilterSet
from netbox_proxbox.forms import (
    ProxmoxVMCloudInitFilterForm,
    ProxmoxVMCloudInitForm,
)
from netbox_proxbox.models import ProxmoxVMCloudInit
from netbox_proxbox.tables import ProxmoxVMCloudInitTable


__all__ = (
    "ProxmoxVMCloudInitView",
    "ProxmoxVMCloudInitListView",
    "ProxmoxVMCloudInitEditView",
    "ProxmoxVMCloudInitDeleteView",
    "ProxmoxVMCloudInitBulkDeleteView",
    "ProxmoxVMCloudInitTabView",
)


@register_model_view(ProxmoxVMCloudInit, "list", path="", detail=False)
class ProxmoxVMCloudInitListView(generic.ObjectListView):
    """Global list of Proxmox VM cloud-init records."""

    queryset = ProxmoxVMCloudInit.objects.select_related("virtual_machine")
    table = ProxmoxVMCloudInitTable
    filterset = ProxmoxVMCloudInitFilterSet
    filterset_form = ProxmoxVMCloudInitFilterForm
    template_name = "netbox_proxbox/proxmoxvmcloudinit_list.html"
    actions = {
        "bulk_delete": {"delete"},
        "export": {"view"},
    }


@register_model_view(ProxmoxVMCloudInit)
class ProxmoxVMCloudInitView(generic.ObjectView):
    """Detail view for one cloud-init record."""

    queryset = ProxmoxVMCloudInit.objects.select_related("virtual_machine")


@register_model_view(ProxmoxVMCloudInit, "add", detail=False)
@register_model_view(ProxmoxVMCloudInit, "edit")
class ProxmoxVMCloudInitEditView(generic.ObjectEditView):
    """Edit view kept for permission parity. The form disables all fields."""

    queryset = ProxmoxVMCloudInit.objects.all()
    form = ProxmoxVMCloudInitForm
    default_return_url = "plugins:netbox_proxbox:proxmoxvmcloudinit_list"


@register_model_view(ProxmoxVMCloudInit, "delete")
class ProxmoxVMCloudInitDeleteView(generic.ObjectDeleteView):
    """Delete a single cloud-init record (e.g. for a removed VM)."""

    queryset = ProxmoxVMCloudInit.objects.all()
    default_return_url = "plugins:netbox_proxbox:proxmoxvmcloudinit_list"


@register_model_view(ProxmoxVMCloudInit, "bulk_delete", detail=False)
class ProxmoxVMCloudInitBulkDeleteView(generic.BulkDeleteView):
    """Bulk delete cloud-init records from the global list."""

    queryset = ProxmoxVMCloudInit.objects.all()
    filterset = ProxmoxVMCloudInitFilterSet
    table = ProxmoxVMCloudInitTable
    default_return_url = "plugins:netbox_proxbox:proxmoxvmcloudinit_list"


@register_model_view(VirtualMachine, "proxmox_cloudinit", path="proxmox-cloudinit")
class ProxmoxVMCloudInitTabView(generic.ObjectView):
    """VM detail tab for the Proxmox cloud-init record (gated on row presence)."""

    queryset = VirtualMachine.objects.all()
    template_name = "netbox_proxbox/vm_proxmox_cloudinit.html"
    tab = ViewTab(
        label="Cloud-init",
        badge=lambda obj: 1 if hasattr(obj, "proxmox_cloudinit") else 0,
        permission="netbox_proxbox.view_proxmoxvmcloudinit",
        weight=1150,
        hide_if_empty=True,
    )

    def get_queryset(self, request: HttpRequest):
        """Restrict parent VMs to those the user may view."""
        return VirtualMachine.objects.restrict(request.user, "view")

    def get_extra_context(self, request: HttpRequest, instance: VirtualMachine):
        """Surface the cloud-init row (if any) for the tab template."""
        cloudinit = ProxmoxVMCloudInit.objects.filter(virtual_machine=instance).first()
        return {"cloudinit": cloudinit}
