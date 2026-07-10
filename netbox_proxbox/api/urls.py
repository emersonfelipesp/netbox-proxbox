"""Register API routes for plugin endpoints and backups."""

from django.urls import include, path
from netbox.api.routers import NetBoxRouter

from . import views
from .ha import HAClusterSummaryAPIView, HAVMResourceAPIView
from .ssh_credentials import (
    NodeHostKeyFingerprintAPIView,
    NodeSSHCredentialByNodeAPIView,
    NodeSSHCredentialSecretsAPIView,
    ProxmoxEndpointHostKeyFingerprintAPIView,
    ProxmoxEndpointSSHCredentialSecretsAPIView,
)
from .views import (
    BackendLogsAPIView,
    ClustersAPIView,
    DashboardAPIView,
    FirecrackerMicroVMsAPIView,
    HomeAPIView,
    InterfacesAPIView,
    IPAddressesAPIView,
    LXCContainersAPIView,
    NodesAPIView,
    ScheduleSyncAPIView,
    VirtualDisksAPIView,
    VirtualMachinesAPIView,
)

app_name = "proxbox"

endpoints_router = NetBoxRouter()
endpoints_router.APIRootView = views.ProxBoxEndpointsView
# Basenames must match Django model_name so utilities.views.get_action_url() /
# DynamicModelChoiceField APISelect resolve plugins-api:…:{model}-list correctly.
endpoints_router.register(
    "proxmox", views.ProxmoxEndpointViewSet, basename="proxmoxendpoint"
)
endpoints_router.register(
    "netbox", views.NetBoxEndpointViewSet, basename="netboxendpoint"
)
endpoints_router.register(
    "fastapi", views.FastAPIEndpointViewSet, basename="fastapiendpoint"
)
endpoints_router.register("pbs", views.PBSEndpointViewSet, basename="pbsendpoint")
endpoints_router.register("pdm", views.PDMEndpointViewSet, basename="pdmendpoint")

router = NetBoxRouter()
router.APIRootView = views.ProxBoxRootView
router.register(
    "proxmox-clusters", views.ProxmoxClusterViewSet, basename="proxmoxcluster"
)
router.register("proxmox-nodes", views.ProxmoxNodeViewSet, basename="proxmoxnode")
router.register(
    "cloud-image-templates",
    views.CloudImageTemplateViewSet,
    basename="cloudimagetemplate",
)
router.register(
    "firecracker-host-pools",
    views.FirecrackerHostPoolViewSet,
    basename="firecrackerhostpool",
)
router.register(
    "firecracker-hosts",
    views.FirecrackerHostViewSet,
    basename="firecrackerhost",
)
router.register(
    "firecracker-image-templates",
    views.FirecrackerImageTemplateViewSet,
    basename="firecrackerimagetemplate",
)
router.register(
    "firecracker-microvms",
    views.FirecrackerMicroVMViewSet,
    basename="firecrackermicrovm",
)
router.register("storage", views.ProxmoxStorageViewSet, basename="storage")
router.register(
    "guest-vm-interfaces",
    views.GuestVMInterfaceViewSet,
    basename="guestvminterface",
)
router.register(
    "guest-vm-interface-addresses",
    views.GuestVMInterfaceAddressViewSet,
    basename="guestvminterfaceaddress",
)
router.register("backups", views.VMBackupViewSet)
router.register("backup-routines", views.BackupRoutineViewSet, basename="backuproutine")
router.register("replications", views.ReplicationViewSet, basename="replication")
router.register("snapshots", views.VMSnapshotViewSet)
router.register("task-history", views.VMTaskHistoryViewSet)
router.register(
    "vm-cloudinit", views.ProxmoxVMCloudInitViewSet, basename="proxmoxvmcloudinit"
)
router.register(
    "vm-templates", views.ProxmoxVMTemplateViewSet, basename="proxmoxvmtemplate"
)
router.register(
    "settings", views.ProxboxPluginSettingsViewSet, basename="proxboxpluginsettings"
)
router.register(
    "ssh-credentials",
    views.NodeSSHCredentialViewSet,
    basename="nodesshcredential",
)
router.register(
    "firewall/security-groups",
    views.ProxmoxFirewallSecurityGroupViewSet,
    basename="proxmoxfirewallsecuritygroup",
)
router.register(
    "firewall/rules",
    views.ProxmoxFirewallRuleViewSet,
    basename="proxmoxfirewallrule",
)
router.register(
    "firewall/ipsets",
    views.ProxmoxFirewallIPSetViewSet,
    basename="proxmoxfirewallipset",
)
router.register(
    "firewall/ipset-entries",
    views.ProxmoxFirewallIPSetEntryViewSet,
    basename="proxmoxfirewallipsetentry",
)
router.register(
    "firewall/aliases",
    views.ProxmoxFirewallAliasViewSet,
    basename="proxmoxfirewallalias",
)
router.register(
    "firewall/options",
    views.ProxmoxFirewallOptionsViewSet,
    basename="proxmoxfirewalloptions",
)
router.register(
    "sdn-fabrics",
    views.ProxmoxSdnFabricViewSet,
    basename="proxmoxsdnfabric",
)
router.register(
    "sdn-controllers",
    views.ProxmoxSdnControllerViewSet,
    basename="proxmoxsdncontroller",
)
router.register(
    "sdn-zones",
    views.ProxmoxSdnZoneViewSet,
    basename="proxmoxsdnzone",
)
router.register(
    "sdn-vnets",
    views.ProxmoxSdnVNetViewSet,
    basename="proxmoxsdnvnet",
)
router.register(
    "sdn-subnets",
    views.ProxmoxSdnSubnetViewSet,
    basename="proxmoxsdnsubnet",
)
router.register(
    "sdn-bindings",
    views.ProxmoxSdnBindingViewSet,
    basename="proxmoxsdnbinding",
)
router.register(
    "sdn-route-maps",
    views.ProxmoxSdnRouteMapViewSet,
    basename="proxmoxsdnroutemap",
)
router.register(
    "sdn-prefix-lists",
    views.ProxmoxSdnPrefixListViewSet,
    basename="proxmoxsdnprefixlist",
)
router.register(
    "datacenter-cpu-models",
    views.ProxmoxDatacenterCpuModelViewSet,
    basename="proxmoxdatacentercpumodel",
)
router.register("pdm-remotes", views.PDMRemoteViewSet, basename="pdmremote")
router.register(
    "deletion-requests",
    views.DeletionRequestViewSet,
    basename="deletionrequest",
)
router.register(
    "apply-jobs",
    views.ProxmoxApplyJobViewSet,
    basename="proxmoxapplyjob",
)

urlpatterns = [
    path(
        "endpoints/",
        include((endpoints_router.urls, "endpoints"), namespace="endpoints"),
    ),
    # Non-model API views mirroring UI pages
    path("home/", HomeAPIView.as_view(), name="home"),
    path("dashboard/", DashboardAPIView.as_view(), name="dashboard"),
    path("resources/clusters/", ClustersAPIView.as_view(), name="api-clusters"),
    path("resources/nodes/", NodesAPIView.as_view(), name="api-nodes"),
    path(
        "resources/virtual-machines/",
        VirtualMachinesAPIView.as_view(),
        name="api-virtual-machines",
    ),
    path(
        "resources/lxc-containers/",
        LXCContainersAPIView.as_view(),
        name="api-lxc-containers",
    ),
    path(
        "resources/firecracker-microvms/",
        FirecrackerMicroVMsAPIView.as_view(),
        name="api-firecracker-microvms",
    ),
    path(
        "resources/interfaces/",
        InterfacesAPIView.as_view(),
        name="api-interfaces",
    ),
    path(
        "resources/ip-addresses/",
        IPAddressesAPIView.as_view(),
        name="api-ip-addresses",
    ),
    path(
        "resources/virtual-disks/",
        VirtualDisksAPIView.as_view(),
        name="api-virtual-disks",
    ),
    path("sync/schedule/", ScheduleSyncAPIView.as_view(), name="api-schedule-sync"),
    path("logs/", BackendLogsAPIView.as_view(), name="api-logs"),
    # Proxbox-api 0.0.12+ HA proxy (mirrors UI views/ha.py + views/vm_ha.py).
    path("ha/summary/", HAClusterSummaryAPIView.as_view(), name="api-ha-summary"),
    path(
        "ha/vm/<int:vmid>/",
        HAVMResourceAPIView.as_view(),
        name="api-ha-vm-resource",
    ),
    # SSH credentials — by-node lookup (metadata-only) + NetBox token-gated secrets.
    path(
        "ssh-credentials/by-node/<int:node_id>/",
        NodeSSHCredentialByNodeAPIView.as_view(),
        name="api-ssh-credential-by-node",
    ),
    path(
        "ssh-credentials/by-node/<int:node_id>/credentials/",
        NodeSSHCredentialSecretsAPIView.as_view(),
        name="api-ssh-credential-secrets",
    ),
    path(
        "ssh-credentials/by-node/<int:node_id>/host-key-fingerprint/",
        NodeHostKeyFingerprintAPIView.as_view(),
        name="api-ssh-credential-node-host-key",
    ),
    path(
        "ssh-credentials/by-endpoint/<int:endpoint_id>/credentials/",
        ProxmoxEndpointSSHCredentialSecretsAPIView.as_view(),
        name="api-ssh-credential-endpoint-secrets",
    ),
    path(
        "ssh-credentials/by-endpoint/<int:endpoint_id>/host-key-fingerprint/",
        ProxmoxEndpointHostKeyFingerprintAPIView.as_view(),
        name="api-ssh-credential-endpoint-host-key",
    ),
    # Model CRUD router (ProxmoxCluster/Node at proxmox-clusters/proxmox-nodes/)
    path("", include(router.urls)),
]
