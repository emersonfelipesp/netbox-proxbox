"""Provide NetBox views for dedicated Proxmox VM template inventory."""

from netbox.views import generic
from utilities.views import register_model_view

from netbox_proxbox.filtersets import ProxmoxVMTemplateFilterSet
from netbox_proxbox.forms import ProxmoxVMTemplateFilterForm, ProxmoxVMTemplateForm
from netbox_proxbox.models import ProxmoxVMTemplate
from netbox_proxbox.tables import ProxmoxVMTemplateTable


__all__ = (
    "ProxmoxVMTemplateView",
    "ProxmoxVMTemplateListView",
    "ProxmoxVMTemplateEditView",
    "ProxmoxVMTemplateDeleteView",
    "ProxmoxVMTemplateBulkDeleteView",
)


_VM_TEMPLATE_QUERYSET = ProxmoxVMTemplate.objects.select_related(
    "proxmox_endpoint",
    "cluster",
    "node",
    "source_vm",
)


@register_model_view(ProxmoxVMTemplate, "list", path="", detail=False)
class ProxmoxVMTemplateListView(generic.ObjectListView):
    """Global list of Proxmox VM templates synced from backend inventory."""

    queryset = _VM_TEMPLATE_QUERYSET
    table = ProxmoxVMTemplateTable
    filterset = ProxmoxVMTemplateFilterSet
    filterset_form = ProxmoxVMTemplateFilterForm
    template_name = "netbox_proxbox/proxmoxvmtemplate_list.html"
    actions = {
        "bulk_delete": {"delete"},
        "export": {"view"},
    }


@register_model_view(ProxmoxVMTemplate)
class ProxmoxVMTemplateView(generic.ObjectView):
    """Detail view for one Proxmox VM template."""

    queryset = _VM_TEMPLATE_QUERYSET
    template_name = "netbox_proxbox/proxmoxvmtemplate.html"


@register_model_view(ProxmoxVMTemplate, "edit")
class ProxmoxVMTemplateEditView(generic.ObjectEditView):
    """Read-only edit surface kept for NetBox table action compatibility."""

    queryset = _VM_TEMPLATE_QUERYSET
    form = ProxmoxVMTemplateForm
    default_return_url = "plugins:netbox_proxbox:proxmoxvmtemplate_list"


@register_model_view(ProxmoxVMTemplate, "delete")
class ProxmoxVMTemplateDeleteView(generic.ObjectDeleteView):
    """Delete a stale Proxmox VM template record."""

    queryset = ProxmoxVMTemplate.objects.all()
    default_return_url = "plugins:netbox_proxbox:proxmoxvmtemplate_list"


@register_model_view(ProxmoxVMTemplate, "bulk_delete", detail=False)
class ProxmoxVMTemplateBulkDeleteView(generic.BulkDeleteView):
    """Bulk delete stale Proxmox VM template records from the global list."""

    queryset = _VM_TEMPLATE_QUERYSET
    filterset = ProxmoxVMTemplateFilterSet
    table = ProxmoxVMTemplateTable
    default_return_url = "plugins:netbox_proxbox:proxmoxvmtemplate_list"
