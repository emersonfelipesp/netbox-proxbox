"""Re-export ProxBox plugin models for stable `from netbox_proxbox.models import ...`."""

from netbox_proxbox.models.apply_job import ProxmoxApplyJob
from netbox_proxbox.models.firewall_alias import ProxmoxFirewallAlias
from netbox_proxbox.models.firewall_ipset import (
    ProxmoxFirewallIPSet,
    ProxmoxFirewallIPSetEntry,
)
from netbox_proxbox.models.firewall_options import ProxmoxFirewallOptions
from netbox_proxbox.models.firewall_rule import ProxmoxFirewallRule
from netbox_proxbox.models.firewall_security_group import ProxmoxFirewallSecurityGroup
from netbox_proxbox.models.sdn_fabric import ProxmoxSdnFabric
from netbox_proxbox.models.sdn_inventory import (
    ProxmoxSdnBinding,
    ProxmoxSdnController,
    ProxmoxSdnSubnet,
    ProxmoxSdnVNet,
    ProxmoxSdnZone,
)
from netbox_proxbox.models.sdn_route_map import ProxmoxSdnRouteMap
from netbox_proxbox.models.sdn_prefix_list import ProxmoxSdnPrefixList
from netbox_proxbox.models.datacenter_cpu_model import ProxmoxDatacenterCpuModel
from netbox_proxbox.models.backup_routine import BackupRoutine
from netbox_proxbox.models.base import PORT_VALIDATORS, CommonProperties, EndpointBase
from netbox_proxbox.models.cloud_image_template import CloudImageTemplate
from netbox_proxbox.models.deletion_request import DeletionRequest
from netbox_proxbox.models.fastapi_endpoint import FastAPIEndpoint
from netbox_proxbox.models.firecracker import (
    FirecrackerHost,
    FirecrackerHostPool,
    FirecrackerImageTemplate,
    FirecrackerMicroVM,
)
from netbox_proxbox.models.netbox_endpoint import NetBoxEndpoint
from netbox_proxbox.models.pbs_endpoint import PBSEndpoint
from netbox_proxbox.models.pdm_endpoint import PDMEndpoint
from netbox_proxbox.models.pdm_remote import PDMRemote, PDMRemoteTypeChoices
from netbox_proxbox.models.plugin_settings import ProxboxPluginSettings
from netbox_proxbox.models.proxmox_cluster import ProxmoxCluster
from netbox_proxbox.models.proxmox_endpoint import ProxmoxEndpoint
from netbox_proxbox.models.proxmox_node import ProxmoxNode
from netbox_proxbox.models.replication import Replication
from netbox_proxbox.models.ssh_credential import NodeSSHCredential
from netbox_proxbox.models.storage import ProxmoxStorage, ProxmoxStorageVirtualDisk
from netbox_proxbox.models.vm_backup import VMBackup
from netbox_proxbox.models.vm_cloudinit import ProxmoxVMCloudInit
from netbox_proxbox.models.vm_snapshot import VMSnapshot
from netbox_proxbox.models.vm_task_history import VMTaskHistory
from netbox_proxbox.models.vm_template import ProxmoxVMTemplate

__all__ = (
    "BackupRoutine",
    "ProxmoxFirewallAlias",
    "ProxmoxFirewallIPSet",
    "ProxmoxFirewallIPSetEntry",
    "ProxmoxFirewallOptions",
    "ProxmoxFirewallRule",
    "ProxmoxFirewallSecurityGroup",
    "ProxmoxSdnFabric",
    "ProxmoxSdnBinding",
    "ProxmoxSdnController",
    "ProxmoxSdnSubnet",
    "ProxmoxSdnVNet",
    "ProxmoxSdnZone",
    "ProxmoxSdnRouteMap",
    "ProxmoxSdnPrefixList",
    "ProxmoxDatacenterCpuModel",
    "CloudImageTemplate",
    "DeletionRequest",
    "FastAPIEndpoint",
    "FirecrackerHost",
    "FirecrackerHostPool",
    "FirecrackerImageTemplate",
    "FirecrackerMicroVM",
    "NetBoxEndpoint",
    "NodeSSHCredential",
    "PBSEndpoint",
    "PDMEndpoint",
    "PDMRemote",
    "PDMRemoteTypeChoices",
    "ProxboxPluginSettings",
    "ProxmoxApplyJob",
    "ProxmoxCluster",
    "ProxmoxEndpoint",
    "ProxmoxNode",
    "ProxmoxVMCloudInit",
    "Replication",
    "ProxmoxStorage",
    "ProxmoxStorageVirtualDisk",
    "VMBackup",
    "VMSnapshot",
    "VMTaskHistory",
    "ProxmoxVMTemplate",
)
