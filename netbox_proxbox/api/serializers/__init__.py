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
    ProxmoxSdnBindingSerializer,
    ProxmoxSdnControllerSerializer,
    ProxmoxSdnFabricSerializer,
    ProxmoxSdnPrefixListSerializer,
    ProxmoxSdnRouteMapSerializer,
    ProxmoxSdnSubnetSerializer,
    ProxmoxSdnVNetSerializer,
    ProxmoxSdnZoneSerializer,
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
from netbox_proxbox.api.serializers.vm_template import (
    NestedProxmoxVMTemplateSerializer,
    ProxmoxVMTemplateSerializer,
)
from netbox_proxbox.api.serializers.pbs_pdm import (
    NestedPBSEndpointSerializer,
    NestedPDMEndpointSerializer,
    PBSEndpointSerializer,
    PDMEndpointSerializer,
    PDMRemoteSerializer,
)
from netbox_proxbox.api.serializers.intent import (
    DeletionRequestSerializer,
    ProxmoxApplyJobSerializer,
)

__all__ = (
    "BackupRoutineSerializer",
    "CloudImageTemplateSerializer",
    "DeletionRequestSerializer",
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
    "NestedPBSEndpointSerializer",
    "NestedPDMEndpointSerializer",
    "NestedProxmoxClusterSerializer",
    "NestedProxmoxEndpointSerializer",
    "NestedProxmoxFirewallIPSetSerializer",
    "NestedProxmoxFirewallSecurityGroupSerializer",
    "NestedTokenSerializer",
    "NetBoxEndpointSerializer",
    "NestedProxmoxStorageSerializer",
    "NodeSSHCredentialSerializer",
    "PBSEndpointSerializer",
    "PDMEndpointSerializer",
    "PDMRemoteSerializer",
    "ProxboxPluginSettingsSerializer",
    "ProxmoxApplyJobSerializer",
    "ProxmoxClusterSerializer",
    "ProxmoxDatacenterCpuModelSerializer",
    "ProxmoxEndpointSerializer",
    "ProxmoxNodeSerializer",
    "NestedProxmoxVMTemplateSerializer",
    "ProxmoxSdnFabricSerializer",
    "ProxmoxSdnPrefixListSerializer",
    "ProxmoxSdnRouteMapSerializer",
    "ProxmoxVMCloudInitSerializer",
    "ProxmoxVMTemplateSerializer",
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
