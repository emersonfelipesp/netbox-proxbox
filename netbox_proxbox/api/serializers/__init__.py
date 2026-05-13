"""Re-export plugin API serializers for `netbox_proxbox.api.serializers`."""

from netbox_proxbox.api.serializers.resource_views import (
    DeviceResourceSerializer,
    InterfaceResourceSerializer,
    IPAddressResourceSerializer,
    ScheduledJobSerializer,
    ScheduleSyncRequestSerializer,
    VirtualDiskResourceSerializer,
    VirtualMachineResourceSerializer,
)
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
from netbox_proxbox.api.serializers.replication import ReplicationSerializer
from netbox_proxbox.api.serializers.settings import ProxboxPluginSettingsSerializer
from netbox_proxbox.api.serializers.ssh_credential import NodeSSHCredentialSerializer
from netbox_proxbox.api.serializers.storage import (
    NestedProxmoxStorageSerializer,
    ProxmoxStorageSerializer,
)
from netbox_proxbox.api.serializers.vm_backup import VMBackupSerializer
from netbox_proxbox.api.serializers.vm_snapshot import VMSnapshotSerializer
from netbox_proxbox.api.serializers.vm_task_history import VMTaskHistorySerializer

__all__ = (
    "BackupRoutineSerializer",
    "DeviceResourceSerializer",
    "FastAPIEndpointSerializer",
    "InterfaceResourceSerializer",
    "IPAddressResourceSerializer",
    "NestedBackupRoutineSerializer",
    "NestedProxmoxClusterSerializer",
    "NestedProxmoxEndpointSerializer",
    "NestedTokenSerializer",
    "NetBoxEndpointSerializer",
    "NestedProxmoxStorageSerializer",
    "NodeSSHCredentialSerializer",
    "ProxboxPluginSettingsSerializer",
    "ProxmoxClusterSerializer",
    "ProxmoxEndpointSerializer",
    "ProxmoxNodeSerializer",
    "ReplicationSerializer",
    "ProxmoxStorageSerializer",
    "ScheduledJobSerializer",
    "ScheduleSyncRequestSerializer",
    "VirtualDiskResourceSerializer",
    "VirtualMachineResourceSerializer",
    "VMBackupSerializer",
    "VMSnapshotSerializer",
    "VMTaskHistorySerializer",
)
