"""Provide Cluster detail tabs for Proxmox storage and summary."""

from __future__ import annotations

from django.core.exceptions import ImproperlyConfigured
from django.http import HttpRequest
from netbox.object_actions import BulkDelete, BulkExport, DeleteObject
from netbox.views import generic
from utilities.views import ViewTab, register_model_view
from virtualization.models import Cluster
from virtualization.views import ClusterVirtualMachinesView

from netbox_proxbox.filtersets import ProxmoxStorageFilterSet
from netbox_proxbox.forms import ProxmoxStorageFilterForm
from netbox_proxbox.models import ProxmoxStorage
from netbox_proxbox.tables import ProxmoxStorageTable
from netbox_proxbox.views.mixins import TableConfigOverrideMixin


__all__ = (
    "ClusterStoragesTabView",
    "ClusterSummaryTabView",
    "enable_cluster_vm_bulk_delete",
)


def enable_cluster_vm_bulk_delete() -> None:
    """Expose VM bulk deletion on NetBox's cluster child-object tab.

    NetBox 4.5 through 4.7 declare the cluster VM tab's actions as
    ``(EditObject, DeleteObject, BulkEdit)``. ``DeleteObject`` is a row action,
    not a multi-object action, so the selected-row toolbar renders only bulk
    edit. Replace that misplaced action with ``BulkDelete`` while preserving
    NetBox's core bulk-delete view, permissions, confirmation, changelog, and
    protected-object handling.
    """
    actions = ClusterVirtualMachinesView.actions
    if BulkDelete in actions:
        return
    if DeleteObject not in actions:
        raise ImproperlyConfigured(
            "netbox-proxbox cannot safely enable cluster VM bulk deletion: "
            "NetBox's ClusterVirtualMachinesView action contract changed."
        )
    ClusterVirtualMachinesView.actions = tuple(
        BulkDelete if action is DeleteObject else action for action in actions
    )


enable_cluster_vm_bulk_delete()


@register_model_view(Cluster, "proxbox-storages", path="storages")
class ClusterStoragesTabView(TableConfigOverrideMixin, generic.ObjectChildrenView):
    """Cluster detail tab listing Proxmox storages for this cluster."""

    queryset = Cluster.objects.all()
    child_model = ProxmoxStorage
    table = ProxmoxStorageTable
    filterset = ProxmoxStorageFilterSet
    filterset_form = ProxmoxStorageFilterForm
    actions = (BulkExport, BulkDelete)
    tab = ViewTab(
        label="Storages",
        badge=lambda obj: ProxmoxStorage.objects.filter(cluster=obj).count(),
        permission="netbox_proxbox.view_proxmoxstorage",
        weight=1000,
    )
    table_exclude = ("cluster",)

    def get_queryset(self, request: HttpRequest):
        """Restrict parent clusters to those the user may view."""
        return Cluster.objects.restrict(request.user, "view")

    def get_children(self, request: HttpRequest, parent: Cluster):
        """Return storages for ``parent`` visible to the current user."""
        return ProxmoxStorage.objects.restrict(request.user, "view").filter(
            cluster=parent
        )


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
