"""CRUD and list views for Proxmox storage rows."""

from netbox.views import generic
from utilities.views import register_model_view

from netbox_proxbox.filtersets import ProxmoxStorageFilterSet
from netbox_proxbox.forms import ProxmoxStorageFilterForm, ProxmoxStorageForm
from netbox_proxbox.models import ProxmoxStorage
from netbox_proxbox.tables import ProxmoxStorageTable

__all__ = (
    "ProxmoxStorageView",
    "ProxmoxStorageListView",
    "ProxmoxStorageEditView",
    "ProxmoxStorageDeleteView",
    "ProxmoxStorageBulkDeleteView",
)


@register_model_view(ProxmoxStorage, "list", path="", detail=False)
class ProxmoxStorageListView(generic.ObjectListView):
    """Global list of synchronized Proxmox storage rows."""

    queryset = ProxmoxStorage.objects.all()
    table = ProxmoxStorageTable
    filterset = ProxmoxStorageFilterSet
    filterset_form = ProxmoxStorageFilterForm
    template_name = "netbox_proxbox/storage_list.html"
    actions = {
        "bulk_delete": {"delete"},
        "export": {"view"},
    }


@register_model_view(ProxmoxStorage)
class ProxmoxStorageView(generic.ObjectView):
    """Detail view for one Proxmox storage row."""

    queryset = ProxmoxStorage.objects.all()


@register_model_view(ProxmoxStorage, "edit")
class ProxmoxStorageEditView(generic.ObjectEditView):
    """Create or edit a Proxmox storage row."""

    queryset = ProxmoxStorage.objects.all()
    form = ProxmoxStorageForm
    default_return_url = "plugins:netbox_proxbox:proxmoxstorage_list"


@register_model_view(ProxmoxStorage, "delete")
class ProxmoxStorageDeleteView(generic.ObjectDeleteView):
    """Delete a single Proxmox storage row."""

    queryset = ProxmoxStorage.objects.all()
    default_return_url = "plugins:netbox_proxbox:proxmoxstorage_list"


@register_model_view(ProxmoxStorage, "bulk_delete", detail=False)
class ProxmoxStorageBulkDeleteView(generic.BulkDeleteView):
    """Bulk delete Proxmox storage rows from the list page."""

    queryset = ProxmoxStorage.objects.all()
    filterset = ProxmoxStorageFilterSet
    table = ProxmoxStorageTable
    default_return_url = "plugins:netbox_proxbox:proxmoxstorage_list"
