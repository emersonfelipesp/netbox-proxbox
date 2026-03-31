"""Provide NetBox CRUD and tab views for VM task history records."""

from django.shortcuts import get_object_or_404

from extras.models import TableConfig
from netbox.views import generic
from utilities.views import ViewTab, register_model_view
from virtualization.models import VirtualMachine

from netbox_proxbox.filtersets import VMTaskHistoryFilterSet
from netbox_proxbox.forms import VMTaskHistoryFilterForm
from netbox_proxbox.models import VMTaskHistory
from netbox_proxbox.tables import VMTaskHistoryTable


__all__ = (
    "VMTaskHistoryView",
    "VMTaskHistoryListView",
    "VMTaskHistoryTabView",
)


@register_model_view(VMTaskHistory)
class VMTaskHistoryView(generic.ObjectView):
    """Detail view for one VM task history record."""

    queryset = VMTaskHistory.objects.all()
    template_name = "netbox_proxbox/vmtaskhistory.html"


@register_model_view(VirtualMachine, "task_history", path="task-history")
class VMTaskHistoryTabView(generic.ObjectChildrenView):
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

    def get_queryset(self, request):
        """Restrict parent VMs to those the user may view."""
        return VirtualMachine.objects.restrict(request.user, "view")

    def get_children(self, request, parent):
        """Return task history rows for ``parent`` visible to the current user."""
        return VMTaskHistory.objects.restrict(request.user, "view").filter(
            virtual_machine=parent
        )

    def get_table(self, data, request, bulk_actions=True):
        """Build the child table, honoring optional ``tableconfig_id`` column overrides."""
        if tableconfig_id := request.GET.get("tableconfig_id"):
            tableconfig = get_object_or_404(TableConfig, pk=tableconfig_id)
            if request.user.is_authenticated:
                table_name = self.table.__name__
                request.user.config.set(
                    f"tables.{table_name}.columns", tableconfig.columns
                )
                request.user.config.set(
                    f"tables.{table_name}.ordering",
                    tableconfig.ordering,
                    commit=True,
                )

        table = self.table(data, exclude=("virtual_machine",))
        table.configure(request)
        return table


class VMTaskHistoryListView(generic.ObjectListView):
    """List view for all VM task history records with filtering."""

    queryset = VMTaskHistory.objects.all()
    table = VMTaskHistoryTable
    filterset = VMTaskHistoryFilterSet
    filterset_form = VMTaskHistoryFilterForm
    actions = {
        "export": {"view"},
    }
