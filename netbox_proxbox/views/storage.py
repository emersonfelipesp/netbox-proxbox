"""CRUD and list views for Proxmox storage rows."""

from django.db.models import Sum

from netbox.views import generic
from utilities.views import register_model_view

from netbox_proxbox.filtersets import ProxmoxStorageFilterSet
from netbox_proxbox.forms import ProxmoxStorageFilterForm, ProxmoxStorageForm
from netbox_proxbox.models import ProxmoxStorage, VMBackup, VMSnapshot
from netbox_proxbox.tables import ProxmoxStorageTable
from virtualization.models import VirtualDisk

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
    template_name = "netbox_proxbox/proxmoxstorage.html"

    def get_extra_context(self, request, instance):
        storage_qs = ProxmoxStorage.objects.restrict(request.user, "view")
        storage = storage_qs.filter(pk=instance.pk).first()
        if storage is None:
            return {}

        virtual_disks = (
            VirtualDisk.objects.restrict(request.user, "view")
            .filter(
                name__startswith=f"{storage.name}:",
                virtual_machine__cluster__name=storage.cluster,
            )
            .select_related("virtual_machine", "virtual_machine__cluster")
            .order_by("virtual_machine__name", "name")
        )
        backups = (
            VMBackup.objects.restrict(request.user, "view")
            .filter(storage=storage)
            .select_related("virtual_machine", "storage")
            .order_by("-creation_time", "virtual_machine__name", "volume_id")
        )
        snapshots = (
            VMSnapshot.objects.restrict(request.user, "view")
            .filter(storage=storage)
            .select_related("virtual_machine", "storage")
            .order_by("virtual_machine__name", "node", "name")
        )

        return {
            "virtual_disks": virtual_disks,
            "backups": backups,
            "snapshots": snapshots,
            "storage_summary": {
                "virtual_disks_count": virtual_disks.count(),
                "virtual_disks_size": virtual_disks.aggregate(total=Sum("size"))[
                    "total"
                ]
                or 0,
                "backups_count": backups.count(),
                "backups_size": backups.aggregate(total=Sum("size"))["total"] or 0,
                "snapshots_count": snapshots.count(),
            },
        }


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
