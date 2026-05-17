"""DRF serializers for netbox-packer models."""

from __future__ import annotations

from netbox.api.serializers import NetBoxModelSerializer
from rest_framework import serializers

from netbox_packer.models import (
    PackerImageBuild,
    PackerImageDefinition,
    PackerPluginSettings,
)

PACKER_DEFAULT_VARIABLE_KEYS = frozenset(
    {
        "vm_storage",
        "cloud_init_storage",
        "bridge",
        "memory_mb",
        "cores",
        "cpu_type",
    }
)


class PackerPluginSettingsSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_packer-api:packerpluginsettings-detail"
    )

    class Meta:
        model = PackerPluginSettings
        fields = (
            "singleton_key",
            "url",
            "display",
            "image_factory_enabled",
            "image_factory_max_concurrent_builds",
            "image_factory_default_job_timeout",
            "image_factory_allow_iso_builds",
            "image_factory_allow_custom_variables",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("singleton_key", "url", "display")


class PackerImageDefinitionSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_packer-api:packerimagedefinition-detail"
    )

    class Meta:
        model = PackerImageDefinition
        fields = (
            "id",
            "url",
            "display",
            "name",
            "slug",
            "description",
            "enabled",
            "builder_type",
            "proxmox_endpoint",
            "target_cluster",
            "target_node",
            "source_template_vmid",
            "default_storage",
            "default_bridge",
            "os_family",
            "os_release",
            "default_ciuser",
            "provisioner_recipe",
            "default_variables",
            "allowed_tenants",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "name", "slug", "enabled")

    def validate_default_variables(self, value: object) -> dict[str, object]:
        if not isinstance(value, dict):
            raise serializers.ValidationError(
                "Default variables must be a JSON object."
            )

        unknown_keys = sorted(set(value) - PACKER_DEFAULT_VARIABLE_KEYS)
        if unknown_keys:
            allowed = ", ".join(sorted(PACKER_DEFAULT_VARIABLE_KEYS))
            unknown = ", ".join(unknown_keys)
            raise serializers.ValidationError(
                f"Unsupported default_variables keys: {unknown}. Allowed keys: {allowed}."
            )
        return value


class PackerImageBuildSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_packer-api:packerimagebuild-detail"
    )

    class Meta:
        model = PackerImageBuild
        fields = (
            "id",
            "url",
            "display",
            "definition",
            "status",
            "backend_build_id",
            "proxmox_endpoint",
            "target_node",
            "output_vmid",
            "output_name",
            "image_version",
            "started_at",
            "completed_at",
            "created_by",
            "netbox_job_id",
            "cloud_image_template",
            "backend_response",
            "error",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "status", "backend_build_id")
