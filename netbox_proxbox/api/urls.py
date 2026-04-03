"""Register API routes for plugin endpoints and backups."""

from django.urls import include, path
from netbox.api.routers import NetBoxRouter

from . import views

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
router.register("clusters", views.ProxmoxClusterViewSet, basename="proxmoxcluster")
router.register("nodes", views.ProxmoxNodeViewSet, basename="proxmoxnode")
router.register("storage", views.ProxmoxStorageViewSet, basename="storage")
router.register("backups", views.VMBackupViewSet)
router.register("backup-routines", views.BackupRoutineViewSet, basename="backuproutine")
router.register("replications", views.ReplicationViewSet, basename="replication")
router.register("snapshots", views.VMSnapshotViewSet)
router.register("task-history", views.VMTaskHistoryViewSet)

urlpatterns = [
    path(
        "endpoints/",
        include((endpoints_router.urls, "endpoints"), namespace="endpoints"),
    ),
    path("", include(router.urls)),
]
