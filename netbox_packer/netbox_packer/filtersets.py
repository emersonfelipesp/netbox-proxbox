"""Minimal filtersets for netbox-packer API queries."""

from __future__ import annotations

from netbox.filtersets import NetBoxModelFilterSet

from netbox_packer.models import (
    PackerImageBuild,
    PackerImageDefinition,
    PackerPluginSettings,
)


class PackerImageDefinitionFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = PackerImageDefinition
        fields = (
            "id",
            "name",
            "slug",
            "enabled",
            "builder_type",
            "proxmox_endpoint",
            "target_cluster",
            "target_node",
            "os_family",
            "provisioner_recipe",
        )


class PackerImageBuildFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = PackerImageBuild
        fields = (
            "id",
            "definition",
            "status",
            "backend_build_id",
            "proxmox_endpoint",
            "target_node",
            "output_vmid",
            "image_version",
            "created_by",
            "netbox_job_id",
            "cloud_image_template",
        )


class PackerPluginSettingsFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = PackerPluginSettings
        fields = ("singleton_key",)
