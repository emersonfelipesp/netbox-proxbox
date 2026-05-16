"""API URL routes for the netbox-pbs plugin."""

from __future__ import annotations

from netbox.api.routers import NetBoxRouter

from netbox_pbs.api import views

app_name = "netbox_pbs-api"

router = NetBoxRouter()
router.register("settings", views.PBSPluginSettingsViewSet)
router.register("servers", views.PBSServerViewSet)
router.register("datastores", views.PBSDatastoreViewSet)
router.register("snapshots", views.PBSSnapshotViewSet)
router.register("jobs", views.PBSJobViewSet)

urlpatterns = router.urls
