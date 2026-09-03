"""NetBox CRUD views for virtual-machine intent."""

from netbox.object_actions import BulkDelete, BulkExport
from netbox.views import generic
from utilities.views import register_model_view

from netbox_proxbox.filtersets import ProxmoxVMIntentFilterSet
from netbox_proxbox.forms import ProxmoxVMIntentFilterForm, ProxmoxVMIntentForm
from netbox_proxbox.models import ProxmoxVMIntent
from netbox_proxbox.tables import ProxmoxVMIntentTable


@register_model_view(ProxmoxVMIntent, "list", path="", detail=False)
class ProxmoxVMIntentListView(generic.ObjectListView):
    queryset = ProxmoxVMIntent.objects.select_related("virtual_machine")
    table = ProxmoxVMIntentTable
    filterset = ProxmoxVMIntentFilterSet
    filterset_form = ProxmoxVMIntentFilterForm
    actions = (BulkExport, BulkDelete)


@register_model_view(ProxmoxVMIntent)
class ProxmoxVMIntentView(generic.ObjectView):
    queryset = ProxmoxVMIntent.objects.select_related("virtual_machine")


@register_model_view(ProxmoxVMIntent, "add", detail=False)
@register_model_view(ProxmoxVMIntent, "edit")
class ProxmoxVMIntentEditView(generic.ObjectEditView):
    queryset = ProxmoxVMIntent.objects.all()
    form = ProxmoxVMIntentForm
    default_return_url = "plugins:netbox_proxbox:proxmoxvmintent_list"


@register_model_view(ProxmoxVMIntent, "delete")
class ProxmoxVMIntentDeleteView(generic.ObjectDeleteView):
    queryset = ProxmoxVMIntent.objects.all()
    default_return_url = "plugins:netbox_proxbox:proxmoxvmintent_list"


@register_model_view(ProxmoxVMIntent, "bulk_delete", detail=False)
class ProxmoxVMIntentBulkDeleteView(generic.BulkDeleteView):
    queryset = ProxmoxVMIntent.objects.all()
    filterset = ProxmoxVMIntentFilterSet
    table = ProxmoxVMIntentTable
    default_return_url = "plugins:netbox_proxbox:proxmoxvmintent_list"
