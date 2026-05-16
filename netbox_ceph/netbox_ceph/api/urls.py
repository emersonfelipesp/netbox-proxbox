"""API URL routes for the netbox-ceph plugin."""

from __future__ import annotations

from netbox.api.routers import NetBoxRouter

from netbox_ceph.api import views

app_name = "netbox_ceph-api"

router = NetBoxRouter()
router.register("settings", views.CephPluginSettingsViewSet)
router.register("clusters", views.CephClusterViewSet)
router.register("daemons", views.CephDaemonViewSet)
router.register("osds", views.CephOSDViewSet)
router.register("pools", views.CephPoolViewSet)
router.register("filesystems", views.CephFilesystemViewSet)
router.register("crush-rules", views.CephCrushRuleViewSet)
router.register("flags", views.CephFlagViewSet)
router.register("health-checks", views.CephHealthCheckViewSet)

urlpatterns = router.urls
