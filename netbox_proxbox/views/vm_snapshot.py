"""Provide NetBox CRUD and tab views for VM snapshot records."""

from django.http import HttpRequest
from netbox.views import generic
from utilities.views import ViewTab, register_model_view
from virtualization.models import VirtualMachine

from netbox_proxbox.filtersets import VMSnapshotFilterSet
from netbox_proxbox.forms import VMSnapshotFilterForm, VMSnapshotForm
from netbox_proxbox.models import VMSnapshot
from netbox_proxbox.tables import VMSnapshotTable
from netbox_proxbox.views.mixins import TableConfigOverrideMixin


__all__ = (
    "VMSnapshotView",
    "VMSnapshotListView",
    "VMSnapshotEditView",
    "VMSnapshotDeleteView",
    "VMSnapshotBulkDeleteView",
    "VMSnapshotTabView",
)


@register_model_view(VMSnapshot, "list", path="", detail=False)
class VMSnapshotListView(generic.ObjectListView):
    """Global list of VM snapshots with export and bulk delete actions."""

    queryset = VMSnapshot.objects.all()
    table = VMSnapshotTable
    filterset = VMSnapshotFilterSet
    filterset_form = VMSnapshotFilterForm
    template_name = "netbox_proxbox/vmsnapshot_list.html"
    actions = {
        "bulk_delete": {"delete"},
        "export": {"view"},
    }


@register_model_view(VMSnapshot)
class VMSnapshotView(generic.ObjectView):
    """Detail view for one VM snapshot."""

    queryset = VMSnapshot.objects.all()


@register_model_view(VMSnapshot, "edit")
class VMSnapshotEditView(generic.ObjectEditView):
    """Create or edit a VM snapshot record."""

    queryset = VMSnapshot.objects.all()
    form = VMSnapshotForm
    default_return_url = "plugins:netbox_proxbox:vmsnapshot_list"


@register_model_view(VMSnapshot, "delete")
class VMSnapshotDeleteView(generic.ObjectDeleteView):
    """Delete a single VM snapshot."""

    queryset = VMSnapshot.objects.all()
    default_return_url = "plugins:netbox_proxbox:vmsnapshot_list"


@register_model_view(VMSnapshot, "bulk_delete", detail=False)
class VMSnapshotBulkDeleteView(generic.BulkDeleteView):
    """Bulk delete VM snapshots from the global list."""

    queryset = VMSnapshot.objects.all()
    filterset = VMSnapshotFilterSet
    table = VMSnapshotTable
    default_return_url = "plugins:netbox_proxbox:vmsnapshot_list"


@register_model_view(VirtualMachine, "snapshots", path="snapshots")
class VMSnapshotTabView(TableConfigOverrideMixin, generic.ObjectChildrenView):
    """VM detail tab listing snapshots for that virtual machine."""

    queryset = VirtualMachine.objects.all()
    child_model = VMSnapshot
    table = VMSnapshotTable
    filterset = VMSnapshotFilterSet
    filterset_form = VMSnapshotFilterForm
    actions = {
        "bulk_delete": {"delete"},
        "export": {"view"},
    }
    tab = ViewTab(
        label="Snapshots",
        badge=lambda obj: VMSnapshot.objects.filter(virtual_machine=obj).count(),
        permission="netbox_proxbox.view_vmsnapshot",
        weight=1100,
    )

    def get_queryset(self, request: HttpRequest):
        """Restrict parent VMs to those the user may view."""
        return VirtualMachine.objects.restrict(request.user, "view")

    def get_children(self, request: HttpRequest, parent: VirtualMachine):
        """Return snapshots for ``parent`` visible to the current user."""
        return VMSnapshot.objects.restrict(request.user, "view").filter(
            virtual_machine=parent
        )
