"""Re-export plugin API serializers for `netbox_proxbox.api.serializers`."""

from netbox_proxbox.api.serializers.firewall import (
    NestedProxmoxFirewallIPSetSerializer,
    NestedProxmoxFirewallSecurityGroupSerializer,
    ProxmoxFirewallAliasSerializer,
    ProxmoxFirewallIPSetEntrySerializer,
    ProxmoxFirewallIPSetSerializer,
    ProxmoxFirewallOptionsSerializer,
    ProxmoxFirewallRuleSerializer,
    ProxmoxFirewallSecurityGroupSerializer,
)
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
from netbox_proxbox.api.serializers.cloud_image_template import (
    CloudImageTemplateSerializer,
    NestedCloudImageTemplateSerializer,
)
from netbox_proxbox.api.serializers.pve_template import (
    PVETemplateBuildRequestSerializer,
    PVETemplateBuildResponseSerializer,
)
from netbox_proxbox.api.serializers.endpoints import (
    FastAPIEndpointSerializer,
    NestedTokenSerializer,
    NetBoxEndpointSerializer,
    ProxmoxEndpointSerializer,
)
from netbox_proxbox.api.serializers.firecracker import (
    FirecrackerHostPoolSerializer,
    FirecrackerHostSerializer,
    FirecrackerImageTemplateSerializer,
    FirecrackerMicroVMSerializer,
    NestedFirecrackerHostPoolSerializer,
    NestedFirecrackerHostSerializer,
    NestedFirecrackerImageTemplateSerializer,
)
from netbox_proxbox.api.serializers.datacenter import (
    ProxmoxDatacenterCpuModelSerializer,
)
from netbox_proxbox.api.serializers.sdn import (
    ProxmoxSdnFabricSerializer,
    ProxmoxSdnPrefixListSerializer,
    ProxmoxSdnRouteMapSerializer,
)
from netbox_proxbox.api.serializers.replication import ReplicationSerializer
from netbox_proxbox.api.serializers.settings import ProxboxPluginSettingsSerializer
from netbox_proxbox.api.serializers.ssh_credential import NodeSSHCredentialSerializer
from netbox_proxbox.api.serializers.storage import (
    NestedProxmoxStorageSerializer,
    ProxmoxStorageSerializer,
)
from netbox_proxbox.api.serializers.vm_backup import VMBackupSerializer
from netbox_proxbox.api.serializers.vm_cloudinit import ProxmoxVMCloudInitSerializer
from netbox_proxbox.api.serializers.vm_snapshot import VMSnapshotSerializer
from netbox_proxbox.api.serializers.vm_task_history import VMTaskHistorySerializer

__all__ = (
    "BackupRoutineSerializer",
    "CloudImageTemplateSerializer",
    "DeviceResourceSerializer",
    "FastAPIEndpointSerializer",
    "FirecrackerHostPoolSerializer",
    "FirecrackerHostSerializer",
    "FirecrackerImageTemplateSerializer",
    "FirecrackerMicroVMSerializer",
    "InterfaceResourceSerializer",
    "IPAddressResourceSerializer",
    "NestedBackupRoutineSerializer",
    "NestedCloudImageTemplateSerializer",
    "NestedFirecrackerHostPoolSerializer",
    "NestedFirecrackerHostSerializer",
    "NestedFirecrackerImageTemplateSerializer",
    "NestedProxmoxClusterSerializer",
    "NestedProxmoxEndpointSerializer",
    "NestedProxmoxFirewallIPSetSerializer",
    "NestedProxmoxFirewallSecurityGroupSerializer",
    "NestedTokenSerializer",
    "NetBoxEndpointSerializer",
    "NestedProxmoxStorageSerializer",
    "NodeSSHCredentialSerializer",
    "ProxboxPluginSettingsSerializer",
    "ProxmoxClusterSerializer",
    "ProxmoxDatacenterCpuModelSerializer",
    "ProxmoxEndpointSerializer",
    "ProxmoxNodeSerializer",
    "ProxmoxSdnFabricSerializer",
    "ProxmoxSdnPrefixListSerializer",
    "ProxmoxSdnRouteMapSerializer",
    "ProxmoxVMCloudInitSerializer",
    "PVETemplateBuildRequestSerializer",
    "PVETemplateBuildResponseSerializer",
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
