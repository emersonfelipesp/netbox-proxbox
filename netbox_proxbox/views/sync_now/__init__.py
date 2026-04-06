"""Individual sync views for calling proxbox-api individual sync endpoints."""

from netbox_proxbox.views.sync_now.cluster import ProxmoxClusterSyncNowView
from netbox_proxbox.views.sync_now.node import ProxmoxNodeSyncNowView
from netbox_proxbox.views.sync_now.storage import ProxmoxStorageSyncNowView
from netbox_proxbox.views.sync_now.vm import VirtualMachineSyncNowView

__all__ = (
    "ProxmoxClusterSyncNowView",
    "ProxmoxNodeSyncNowView",
    "ProxmoxStorageSyncNowView",
    "VirtualMachineSyncNowView",
)
