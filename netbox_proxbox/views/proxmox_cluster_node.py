"""Detail views for the reflected ``ProxmoxCluster`` and ``ProxmoxNode`` rows.

Both models have always declared ``get_absolute_url()`` pointing at
``plugins:netbox_proxbox:proxmoxcluster`` / ``:proxmoxnode``, but no view was
ever registered under those names and ``urls.py`` never mounted
``get_model_urls()`` for them. The reverse therefore failed for every caller
(netbox-proxbox issue #618: a core ``virtualization.Cluster`` detail page raised
``NoReverseMatch`` through the Sync-Now template extension).

The models now guard the reverse and return ``""`` instead of raising, so the
page no longer 500s -- but that only converted a crash into three dead UI
surfaces: the Sync Now button on core Cluster/Device pages, the ``linkify``
columns in ``ProxmoxClusterTable``/``ProxmoxNodeTable``, and the registered
``proxbox_sync_now`` action views, which nothing could route to. Sync Now URLs
are now reversed from the tracking row's registered model action rather than
derived from its detail URL (issue #294).

Registering a real detail view under the bare model name -- and mounting it in
``urls.py`` -- is what makes all three work again.
"""

from netbox.views import generic
from utilities.views import register_model_view

from netbox_proxbox.models import ProxmoxCluster, ProxmoxNode

__all__ = (
    "ProxmoxClusterView",
    "ProxmoxNodeView",
)


@register_model_view(ProxmoxCluster)
class ProxmoxClusterView(generic.ObjectView):
    """Detail view for one reflected Proxmox cluster row."""

    queryset = ProxmoxCluster.objects.select_related("endpoint", "netbox_cluster")
    template_name = "netbox_proxbox/proxmoxcluster.html"


@register_model_view(ProxmoxNode)
class ProxmoxNodeView(generic.ObjectView):
    """Detail view for one reflected Proxmox node row."""

    queryset = ProxmoxNode.objects.select_related(
        "endpoint", "proxmox_cluster", "netbox_device"
    )
    template_name = "netbox_proxbox/proxmoxnode.html"
