"""Provide NetBox CRUD and tab views for VM task history records."""

from django.http import HttpRequest
from netbox.views import generic
from utilities.views import ViewTab, register_model_view
from virtualization.models import VirtualMachine

from netbox_proxbox.filtersets import VMTaskHistoryFilterSet
from netbox_proxbox.forms import VMTaskHistoryFilterForm, VMTaskHistoryForm
from netbox_proxbox.models import VMTaskHistory
from netbox_proxbox.tables import VMTaskHistoryTable
from netbox_proxbox.views.mixins import TableConfigOverrideMixin


__all__ = (
    "VMTaskHistoryView",
    "VMTaskHistoryListView",
    "VMTaskHistoryEditView",
    "VMTaskHistoryDeleteView",
    "VMTaskHistoryBulkDeleteView",
    "VMTaskHistoryTabView",
)


@register_model_view(VMTaskHistory)
class VMTaskHistoryView(generic.ObjectView):
    """Detail view for one VM task history record."""

    queryset = VMTaskHistory.objects.all()
    template_name = "netbox_proxbox/vmtaskhistory.html"


@register_model_view(VirtualMachine, "task_history", path="task-history")
class VMTaskHistoryTabView(TableConfigOverrideMixin, generic.ObjectChildrenView):
    """VM detail tab listing task history records for that virtual machine."""

    queryset = VirtualMachine.objects.all()
    child_model = VMTaskHistory
    table = VMTaskHistoryTable
    filterset = VMTaskHistoryFilterSet
    filterset_form = VMTaskHistoryFilterForm
    actions = {
        "export": {"view"},
    }
    tab = ViewTab(
        label="Task History",
        badge=lambda obj: VMTaskHistory.objects.filter(virtual_machine=obj).count(),
        permission="netbox_proxbox.view_vmtaskhistory",
        weight=1200,
    )

    def get_queryset(self, request: HttpRequest):
        """Restrict parent VMs to those the user may view."""
        return VirtualMachine.objects.restrict(request.user, "view")

    def get_children(self, request: HttpRequest, parent: VirtualMachine):
        """Return task history rows for ``parent`` visible to the current user."""
        return VMTaskHistory.objects.restrict(request.user, "view").filter(
            virtual_machine=parent
        )


@register_model_view(VMTaskHistory, "list", path="", detail=False)
class VMTaskHistoryListView(generic.ObjectListView):
    """List view for all VM task history records with filtering."""

    queryset = VMTaskHistory.objects.all()
    table = VMTaskHistoryTable
    filterset = VMTaskHistoryFilterSet
    filterset_form = VMTaskHistoryFilterForm
    actions = {
        "bulk_delete": {"delete"},
        "export": {"view"},
    }


@register_model_view(VMTaskHistory, "edit")
class VMTaskHistoryEditView(generic.ObjectEditView):
    """Create or edit a VM task history record."""

    queryset = VMTaskHistory.objects.all()
    form = VMTaskHistoryForm
    default_return_url = "plugins:netbox_proxbox:vmtaskhistory_list"


@register_model_view(VMTaskHistory, "delete")
class VMTaskHistoryDeleteView(generic.ObjectDeleteView):
    """Delete a single VM task history record."""

    queryset = VMTaskHistory.objects.all()
    default_return_url = "plugins:netbox_proxbox:vmtaskhistory_list"


@register_model_view(VMTaskHistory, "bulk_delete", detail=False)
class VMTaskHistoryBulkDeleteView(generic.BulkDeleteView):
    """Bulk delete VM task history records."""

    queryset = VMTaskHistory.objects.all()
    filterset = VMTaskHistoryFilterSet
    table = VMTaskHistoryTable
    default_return_url = "plugins:netbox_proxbox:vmtaskhistory_list"
