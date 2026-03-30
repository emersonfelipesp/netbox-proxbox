"""Register API routes for plugin endpoints, sync processes, and backups."""

from django.urls import include, path

from netbox.api.routers import NetBoxRouter

from . import views

app_name = "proxbox"

endpoints_router = NetBoxRouter()
endpoints_router.APIRootView = views.ProxBoxEndpointsView
endpoints_router.register(
    "proxmox", views.ProxmoxEndpointViewSet, basename="proxmox-endpoint"
)
endpoints_router.register(
    "netbox", views.NetBoxEndpointViewSet, basename="netbox-endpoint"
)
endpoints_router.register(
    "fastapi", views.FastAPIEndpointViewSet, basename="fastapi-endpoint"
)

router = NetBoxRouter()
router.APIRootView = views.ProxBoxRootView
router.register("sync-processes", views.SyncProcessViewSet)
router.register("backups", views.VMBackupViewSet)
router.register("snapshots", views.VMSnapshotViewSet)

urlpatterns = [
    path(
        "endpoints/",
        include((endpoints_router.urls, "endpoints"), namespace="endpoints"),
    ),
    path("", include(router.urls)),
]
