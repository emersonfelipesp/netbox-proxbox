"""Provide NetBox CRUD and tab views for VM backup records."""

from django.shortcuts import render

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
    queryset = VMBackup.objects.all()


@register_model_view(VMBackup, "edit")
class VMBackupEditView(generic.ObjectEditView):
    queryset = VMBackup.objects.all()
    form = VMBackupForm
    default_return_url = "plugins:netbox_proxbox:vmbackup_list"


@register_model_view(VMBackup, "delete")
class VMBackupDeleteView(generic.ObjectDeleteView):
    queryset = VMBackup.objects.all()
    default_return_url = "plugins:netbox_proxbox:vmbackup_list"


@register_model_view(VMBackup, "bulk_delete", detail=False)
class VMBackupBulkDeleteView(generic.BulkDeleteView):
    queryset = VMBackup.objects.all()
    filterset = VMBackupFilterSet
    table = VMBackupTable
    default_return_url = "plugins:netbox_proxbox:vmbackup_list"


@register_model_view(VirtualMachine, "backups", path="backups")
class VMBackupTabView(generic.ObjectView):
    queryset = VirtualMachine.objects.all()
    template_name = "netbox_proxbox/virtual_machine_backups.html"
    tab = ViewTab(
        label="Backups",
        badge=lambda obj: VMBackup.objects.filter(virtual_machine=obj).count(),
        permission="netbox_proxbox.view_vmbackup",
        weight=1000,
    )

    def get(self, request, pk):
        instance = VirtualMachine.objects.get(pk=pk)
        table = VMBackupTable(VMBackup.objects.filter(virtual_machine=instance))
        table.configure(request)
        table.exclude = ("virtual_machine",)
        return render(
            request,
            self.template_name,
            {
                "object": instance,
                "table": table,
                "tab": self.tab,
            },
        )
