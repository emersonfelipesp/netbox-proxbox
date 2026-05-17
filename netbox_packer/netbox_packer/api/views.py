"""DRF viewsets for the netbox-packer plugin API."""

from __future__ import annotations

from netbox.api.viewsets import NetBoxModelViewSet

from netbox_packer import filtersets
from netbox_packer.api import serializers
from netbox_packer.models import (
    PackerImageBuild,
    PackerImageDefinition,
    PackerPluginSettings,
)

_READ_ONLY_HTTP_METHODS = ("get", "head", "options")


class PackerPluginSettingsViewSet(NetBoxModelViewSet):
    queryset = PackerPluginSettings.objects.all()
    serializer_class = serializers.PackerPluginSettingsSerializer
    filterset_class = filtersets.PackerPluginSettingsFilterSet


class PackerImageDefinitionViewSet(NetBoxModelViewSet):
    queryset = (
        PackerImageDefinition.objects.select_related(
            "proxmox_endpoint",
            "target_cluster",
        )
        .prefetch_related("allowed_tenants")
        .all()
    )
    serializer_class = serializers.PackerImageDefinitionSerializer
    filterset_class = filtersets.PackerImageDefinitionFilterSet


class PackerImageBuildViewSet(NetBoxModelViewSet):
    queryset = PackerImageBuild.objects.select_related(
        "definition",
        "proxmox_endpoint",
        "created_by",
        "cloud_image_template",
    ).all()
    serializer_class = serializers.PackerImageBuildSerializer
    filterset_class = filtersets.PackerImageBuildFilterSet
    http_method_names = _READ_ONLY_HTTP_METHODS
