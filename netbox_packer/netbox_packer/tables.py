"""Minimal django-tables2 layouts for future netbox-packer UI views."""

from __future__ import annotations

from netbox.tables import NetBoxTable

from netbox_packer.models import (
    PackerImageBuild,
    PackerImageDefinition,
    PackerPluginSettings,
)


class PackerImageDefinitionTable(NetBoxTable):
    class Meta(NetBoxTable.Meta):
        model = PackerImageDefinition
        fields = ("pk", "id", "name", "slug", "enabled", "builder_type", "actions")
        default_columns = ("name", "slug", "enabled", "builder_type")


class PackerImageBuildTable(NetBoxTable):
    class Meta(NetBoxTable.Meta):
        model = PackerImageBuild
        fields = (
            "pk",
            "id",
            "definition",
            "status",
            "backend_build_id",
            "target_node",
            "output_vmid",
            "image_version",
            "started_at",
            "completed_at",
            "actions",
        )
        default_columns = (
            "definition",
            "status",
            "target_node",
            "output_vmid",
            "image_version",
        )


class PackerPluginSettingsTable(NetBoxTable):
    class Meta(NetBoxTable.Meta):
        model = PackerPluginSettings
        fields = ("pk", "singleton_key", "image_factory_enabled", "actions")
        default_columns = ("singleton_key", "image_factory_enabled")
