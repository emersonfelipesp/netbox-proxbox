"""Provide NetBox CRUD and tab views for VM backup records."""

from django.shortcuts import get_object_or_404

from extras.models import TableConfig
from netbox.views import generic
from utilities.views import ViewTab, register_model_view
from virtualization.models import VirtualMachine

from netbox_proxbox.filtersets import VMBackupFilterSet
from netbox_proxbox.forms import VMBackupFilterForm, VMBackupForm
from netbox_proxbox.models import VMBackup
from netbox_proxbox.tables import VMBackupTable


__all__ = (
    "VMBackupView",
    "VMBackupListView",
    "VMBackupEditView",
    "VMBackupDeleteView",
    "VMBackupBulkDeleteView",
    "VMBackupTabView",
)


@register_model_view(VMBackup, "list", path="", detail=False)
class VMBackupListView(generic.ObjectListView):
    """Global list of VM backups with export and bulk delete actions."""

    queryset = VMBackup.objects.all()
    table = VMBackupTable
    filterset = VMBackupFilterSet
    filterset_form = VMBackupFilterForm
    template_name = "netbox_proxbox/vmbackup_list.html"
    actions = {
        "bulk_delete": {"delete"},
        "export": {"view"},
    }


@register_model_view(VMBackup)
class VMBackupView(generic.ObjectView):
    """Detail view for one VM backup."""

    queryset = VMBackup.objects.all()


@register_model_view(VMBackup, "edit")
class VMBackupEditView(generic.ObjectEditView):
    """Create or edit a VM backup record."""

    queryset = VMBackup.objects.all()
    form = VMBackupForm
    default_return_url = "plugins:netbox_proxbox:vmbackup_list"


@register_model_view(VMBackup, "delete")
class VMBackupDeleteView(generic.ObjectDeleteView):
    """Delete a single VM backup."""

    queryset = VMBackup.objects.all()
    default_return_url = "plugins:netbox_proxbox:vmbackup_list"


@register_model_view(VMBackup, "bulk_delete", detail=False)
class VMBackupBulkDeleteView(generic.BulkDeleteView):
    """Bulk delete VM backups from the global list."""

    queryset = VMBackup.objects.all()
    filterset = VMBackupFilterSet
    table = VMBackupTable
    default_return_url = "plugins:netbox_proxbox:vmbackup_list"


@register_model_view(VirtualMachine, "backups", path="backups")
class VMBackupTabView(generic.ObjectChildrenView):
    """VM detail tab listing backups for that virtual machine."""

    queryset = VirtualMachine.objects.all()
    child_model = VMBackup
    table = VMBackupTable
    filterset = VMBackupFilterSet
    filterset_form = VMBackupFilterForm
    actions = {
        "bulk_delete": {"delete"},
        "export": {"view"},
    }
    tab = ViewTab(
        label="Backups",
        badge=lambda obj: VMBackup.objects.filter(virtual_machine=obj).count(),
        permission="netbox_proxbox.view_vmbackup",
        weight=1000,
    )

    def get_queryset(self, request):
        """Restrict parent VMs to those the user may view."""
        return VirtualMachine.objects.restrict(request.user, "view")

    def get_children(self, request, parent):
        """Return backups for ``parent`` visible to the current user."""
        return VMBackup.objects.restrict(request.user, "view").filter(
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
        if "pk" in table.base_columns and bulk_actions:
            table.columns.show("pk")
        table.configure(request)
        return table
