"""Re-export ProxBox plugin models for stable `from netbox_proxbox.models import ...`."""

from netbox_proxbox.models.base import PORT_VALIDATORS, CommonProperties, EndpointBase
from netbox_proxbox.models.fastapi_endpoint import FastAPIEndpoint
from netbox_proxbox.models.netbox_endpoint import NetBoxEndpoint
from netbox_proxbox.models.proxmox_endpoint import ProxmoxEndpoint
from netbox_proxbox.models.sync_process import SyncProcess
from netbox_proxbox.models.vm_backup import VMBackup
from netbox_proxbox.models.vm_snapshot import VMSnapshot

__all__ = (
    "FastAPIEndpoint",
    "NetBoxEndpoint",
    "ProxmoxEndpoint",
    "SyncProcess",
    "VMBackup",
    "VMSnapshot",
)
