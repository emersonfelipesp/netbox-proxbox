"""Re-export plugin API serializers for `netbox_proxbox.api.serializers`."""

from netbox_proxbox.api.serializers.backup_routine import (
    BackupRoutineSerializer,
    NestedBackupRoutineSerializer,
)
from netbox_proxbox.api.serializers.cluster import (
    NestedProxmoxClusterSerializer,
    NestedProxmoxEndpointSerializer,
    ProxmoxClusterSerializer,
    ProxmoxNodeSerializer,
)
from netbox_proxbox.api.serializers.endpoints import (
    FastAPIEndpointSerializer,
    NestedTokenSerializer,
    NetBoxEndpointSerializer,
    ProxmoxEndpointSerializer,
)
from netbox_proxbox.api.serializers.storage import (
    NestedProxmoxStorageSerializer,
    ProxmoxStorageSerializer,
)
from netbox_proxbox.api.serializers.vm_backup import VMBackupSerializer
from netbox_proxbox.api.serializers.vm_snapshot import VMSnapshotSerializer
from netbox_proxbox.api.serializers.vm_task_history import VMTaskHistorySerializer

__all__ = (
    "BackupRoutineSerializer",
    "FastAPIEndpointSerializer",
    "NestedBackupRoutineSerializer",
    "NestedProxmoxClusterSerializer",
    "NestedProxmoxEndpointSerializer",
    "NestedTokenSerializer",
    "NetBoxEndpointSerializer",
    "NestedProxmoxStorageSerializer",
    "ProxmoxClusterSerializer",
    "ProxmoxEndpointSerializer",
    "ProxmoxNodeSerializer",
    "ProxmoxStorageSerializer",
    "VMBackupSerializer",
    "VMSnapshotSerializer",
    "VMTaskHistorySerializer",
)
