"""Re-export plugin API serializers for `netbox_proxbox.api.serializers`."""

from netbox_proxbox.api.serializers.endpoints import (
    FastAPIEndpointSerializer,
    NestedTokenSerializer,
    NetBoxEndpointSerializer,
    ProxmoxEndpointSerializer,
)
from netbox_proxbox.api.serializers.storage import ProxmoxStorageSerializer
from netbox_proxbox.api.serializers.vm_backup import VMBackupSerializer
from netbox_proxbox.api.serializers.vm_snapshot import VMSnapshotSerializer

__all__ = (
    "FastAPIEndpointSerializer",
    "NestedTokenSerializer",
    "NetBoxEndpointSerializer",
    "ProxmoxEndpointSerializer",
    "ProxmoxStorageSerializer",
    "VMBackupSerializer",
    "VMSnapshotSerializer",
)
