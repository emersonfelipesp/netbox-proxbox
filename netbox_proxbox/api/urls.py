"""Register API routes for plugin endpoints and backups."""

from django.urls import include, path
from netbox.api.routers import NetBoxRouter

from . import views
from .views import (
    BackendLogsAPIView,
    ClustersAPIView,
    DashboardAPIView,
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

router = NetBoxRouter()
router.APIRootView = views.ProxBoxRootView
router.register(
    "proxmox-clusters", views.ProxmoxClusterViewSet, basename="proxmoxcluster"
)
router.register("proxmox-nodes", views.ProxmoxNodeViewSet, basename="proxmoxnode")
router.register("storage", views.ProxmoxStorageViewSet, basename="storage")
router.register("backups", views.VMBackupViewSet)
router.register("backup-routines", views.BackupRoutineViewSet, basename="backuproutine")
router.register("replications", views.ReplicationViewSet, basename="replication")
router.register("snapshots", views.VMSnapshotViewSet)
router.register("task-history", views.VMTaskHistoryViewSet)
router.register(
    "settings", views.ProxboxPluginSettingsViewSet, basename="proxboxpluginsettings"
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
    # Model CRUD router (ProxmoxCluster/Node at proxmox-clusters/proxmox-nodes/)
    path("", include(router.urls)),
]
