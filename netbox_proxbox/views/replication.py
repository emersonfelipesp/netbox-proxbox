"""Provide NetBox CRUD views for Replication records."""

from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from extras.models import TableConfig
from netbox.views import generic
from utilities.views import ViewTab, register_model_view
from virtualization.models import VirtualMachine

from netbox_proxbox.filtersets import ReplicationFilterSet
from netbox_proxbox.forms import ReplicationFilterForm, ReplicationForm
from netbox_proxbox.models import Replication
from netbox_proxbox.tables import ReplicationTable

__all__ = (
    "ReplicationView",
    "ReplicationListView",
    "ReplicationEditView",
    "ReplicationDeleteView",
    "ReplicationBulkDeleteView",
    "ReplicationTabView",
)


@register_model_view(Replication, "list", path="", detail=False)
class ReplicationListView(generic.ObjectListView):
    """Global list of replications with export and bulk delete actions."""

    queryset = Replication.objects.select_related("virtual_machine", "proxmox_node")
    table = ReplicationTable
    filterset = ReplicationFilterSet
    filterset_form = ReplicationFilterForm
    template_name = "netbox_proxbox/replication_list.html"
    actions = {
        "bulk_delete": {"delete"},
        "export": {"view"},
    }


@register_model_view(Replication)
class ReplicationView(generic.ObjectView):
    """Detail view for one replication."""

    queryset = Replication.objects.select_related("virtual_machine", "proxmox_node")
    template_name = "netbox_proxbox/replication.html"


@register_model_view(Replication, "edit")
class ReplicationEditView(generic.ObjectEditView):
    """Create or edit a replication record."""

    queryset = Replication.objects.all()
    form = ReplicationForm
    default_return_url = "plugins:netbox_proxbox:replication_list"


@register_model_view(Replication, "delete")
class ReplicationDeleteView(generic.ObjectDeleteView):
    """Delete a single replication."""

    queryset = Replication.objects.all()
    default_return_url = "plugins:netbox_proxbox:replication_list"


@register_model_view(Replication, "bulk_delete", detail=False)
class ReplicationBulkDeleteView(generic.BulkDeleteView):
    """Bulk delete replications from the global list."""

    queryset = Replication.objects.select_related("virtual_machine", "proxmox_node")
    filterset = ReplicationFilterSet
    table = ReplicationTable
    default_return_url = "plugins:netbox_proxbox:replication_list"


@register_model_view(VirtualMachine, "replications", path="replications")
class ReplicationTabView(generic.ObjectChildrenView):
    """VM detail tab listing replication records for that virtual machine."""

    queryset = VirtualMachine.objects.all()
    child_model = Replication
    table = ReplicationTable
    filterset = ReplicationFilterSet
    filterset_form = ReplicationFilterForm
    actions = {
        "bulk_delete": {"delete"},
        "export": {"view"},
    }
    tab = ViewTab(
        label="Replications",
        badge=lambda obj: Replication.objects.filter(virtual_machine=obj).count(),
        permission="netbox_proxbox.view_replication",
        weight=1150,
    )

    def get_queryset(self, request: HttpRequest) -> object:
        """Restrict parent VMs to those the user may view."""
        return VirtualMachine.objects.restrict(request.user, "view")

    def get_children(
        self, request: HttpRequest, parent: VirtualMachine
    ) -> object:
        """Return replications for ``parent`` visible to the current user."""
        return Replication.objects.restrict(request.user, "view").filter(
            virtual_machine=parent
        )

    def get_table(
        self, data: object, request: HttpRequest, bulk_actions: bool = True
    ) -> ReplicationTable:
        """Build the child table, honoring optional ``tableconfig_id`` overrides."""
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
