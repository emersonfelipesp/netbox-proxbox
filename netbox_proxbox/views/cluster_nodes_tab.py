"""Cluster and node tab view for Proxmox endpoint detail page."""

from django.db.models import Prefetch
from django.http import HttpRequest
from netbox.views import generic
from utilities.views import ViewTab, register_model_view

from netbox_proxbox.models import ProxmoxCluster, ProxmoxEndpoint, ProxmoxNode
from netbox_proxbox.tables import ProxmoxClusterTable, ProxmoxNodeTable


@register_model_view(ProxmoxEndpoint, "cluster_nodes", path="cluster-nodes")
class ProxmoxEndpointClusterNodesTabView(generic.ObjectView):
    """
    Tab view for displaying cluster and node information for a Proxmox endpoint.
    Shows cluster details and a table of nodes discovered from this endpoint.
    """

    queryset = ProxmoxEndpoint.objects.all()
    template_name = "netbox_proxbox/proxmoxendpoint_cluster_nodes.html"
    tab = ViewTab(
        label="Cluster Nodes",
        permission="netbox_proxbox.view_proxmoxendpoint",
        weight=1000,
    )

    def get_extra_context(
        self, request: HttpRequest, instance: ProxmoxEndpoint
    ) -> dict[str, object]:
        """Build cluster and node tables for the template."""
        # Fetch cluster(s) for this endpoint with prefetched nodes
        clusters = ProxmoxCluster.objects.filter(endpoint=instance).prefetch_related(
            Prefetch(
                "nodes",
                queryset=ProxmoxNode.objects.select_related(
                    "netbox_device", "proxmox_cluster"
                ).order_by("name"),
            ),
            "netbox_cluster",
        )

        # Fetch all nodes for this endpoint (includes standalone nodes)
        nodes = ProxmoxNode.objects.filter(endpoint=instance).select_related(
            "proxmox_cluster", "netbox_device"
        )

        # Build the node table
        node_table = ProxmoxNodeTable(nodes)
        node_table.configure(request)

        # Build cluster table if any
        cluster_table = None
        if clusters.exists():
            cluster_table = ProxmoxClusterTable(clusters)
            cluster_table.configure(request)

        return {
            "clusters": clusters,
            "cluster_table": cluster_table,
            "nodes": nodes,
            "node_table": node_table,
            "has_data": clusters.exists() or nodes.exists(),
        }
