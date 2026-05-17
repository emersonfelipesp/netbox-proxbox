"""API URL routes for the netbox-packer plugin."""

from __future__ import annotations

from netbox.api.routers import NetBoxRouter

from netbox_packer.api import views

app_name = "netbox_packer-api"

router = NetBoxRouter()
router.register("image-definitions", views.PackerImageDefinitionViewSet)
router.register("image-builds", views.PackerImageBuildViewSet)
router.register("plugin-settings", views.PackerPluginSettingsViewSet)

urlpatterns = router.urls
