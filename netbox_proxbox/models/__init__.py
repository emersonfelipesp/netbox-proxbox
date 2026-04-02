"""Re-export ProxBox plugin models for stable `from netbox_proxbox.models import ...`."""

from netbox_proxbox.models.base import PORT_VALIDATORS, CommonProperties, EndpointBase
from netbox_proxbox.models.fastapi_endpoint import FastAPIEndpoint
from netbox_proxbox.models.netbox_endpoint import NetBoxEndpoint
from netbox_proxbox.models.plugin_settings import ProxboxPluginSettings
from netbox_proxbox.models.proxmox_cluster import ProxmoxCluster
from netbox_proxbox.models.proxmox_endpoint import ProxmoxEndpoint
from netbox_proxbox.models.proxmox_node import ProxmoxNode
from netbox_proxbox.models.storage import ProxmoxStorage, ProxmoxStorageVirtualDisk
from netbox_proxbox.models.vm_backup import VMBackup
from netbox_proxbox.models.vm_snapshot import VMSnapshot
from netbox_proxbox.models.vm_task_history import VMTaskHistory

__all__ = (
    "FastAPIEndpoint",
    "NetBoxEndpoint",
    "ProxboxPluginSettings",
    "ProxmoxCluster",
    "ProxmoxEndpoint",
    "ProxmoxNode",
    "ProxmoxStorage",
    "ProxmoxStorageVirtualDisk",
    "VMBackup",
    "VMSnapshot",
    "VMTaskHistory",
)
