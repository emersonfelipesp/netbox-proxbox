"""Provide Cluster detail tabs for Proxmox storage and summary."""

from __future__ import annotations

from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from extras.models import TableConfig
from netbox.views import generic
from utilities.views import ViewTab, register_model_view
from virtualization.models import Cluster

from netbox_proxbox.filtersets import ProxmoxStorageFilterSet
from netbox_proxbox.forms import ProxmoxStorageFilterForm
from netbox_proxbox.models import ProxmoxStorage
from netbox_proxbox.tables import ProxmoxStorageTable


__all__ = (
    "ClusterStoragesTabView",
    "ClusterSummaryTabView",
)


@register_model_view(Cluster, "proxbox-storages", path="storages")
class ClusterStoragesTabView(generic.ObjectChildrenView):
    """Cluster detail tab listing Proxmox storages for this cluster."""

    queryset = Cluster.objects.all()
    child_model = ProxmoxStorage
    table = ProxmoxStorageTable
    filterset = ProxmoxStorageFilterSet
    filterset_form = ProxmoxStorageFilterForm
    actions = {
        "bulk_delete": {"delete"},
        "export": {"view"},
    }
    tab = ViewTab(
        label="Storages",
        badge=lambda obj: ProxmoxStorage.objects.filter(cluster=obj).count(),
        permission="netbox_proxbox.view_proxmoxstorage",
        weight=1000,
    )

    def get_queryset(self, request: HttpRequest) -> object:
        """Restrict parent clusters to those the user may view."""
        return Cluster.objects.restrict(request.user, "view")

    def get_children(self, request: HttpRequest, parent: Cluster) -> object:
        """Return storages for ``parent`` visible to the current user."""
        return ProxmoxStorage.objects.restrict(request.user, "view").filter(
            cluster=parent
        )

    def get_table(
        self, data: object, request: HttpRequest, bulk_actions: bool = True
    ) -> ProxmoxStorageTable:
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

        table = self.table(data, exclude=("cluster",))
        if "pk" in table.base_columns and bulk_actions:
            table.columns.show("pk")
        table.configure(request)
        return table


@register_model_view(Cluster, "proxbox-summary", path="summary")
class ClusterSummaryTabView(generic.ObjectView):
    """Cluster detail tab showing Proxmox summary and metrics."""

    queryset = Cluster.objects.all()
    template_name = "netbox_proxbox/cluster/cluster_summary.html"
    tab = ViewTab(
        label="Proxmox Summary",
        permission="netbox_proxbox.view_proxmoxstorage",
        weight=1100,
    )

    def get_extra_context(
        self, request: HttpRequest, instance: Cluster
    ) -> dict[str, object]:
        """Gather Proxmox-related data for this cluster."""
        context: dict[str, object] = {
            "cluster": instance,
        }

        # Get storage summary
        storages = ProxmoxStorage.objects.restrict(request.user, "view").filter(
            cluster=instance
        )
        context["storage_count"] = storages.count()
        context["storages"] = storages[:10]  # Show first 10 for preview

        # Get linked ProxmoxEndpoint if any matches this cluster name
        from netbox_proxbox.models import ProxmoxEndpoint

        proxmox_endpoints = ProxmoxEndpoint.objects.restrict(
            request.user, "view"
        ).filter(name=instance.name)
        context["proxmox_endpoint"] = proxmox_endpoints.first()

        return context
