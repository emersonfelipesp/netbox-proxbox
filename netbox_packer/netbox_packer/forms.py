"""Stub NetBox forms for netbox-packer.

Real edit and filter fields land in PHASE3.
"""

from __future__ import annotations

from netbox.forms import NetBoxModelForm

from netbox_packer.models import (
    PackerImageBuild,
    PackerImageDefinition,
    PackerPluginSettings,
)


class PackerImageDefinitionForm(NetBoxModelForm):
    class Meta:
        model = PackerImageDefinition
        fields: tuple[str, ...] = ()


class PackerImageBuildForm(NetBoxModelForm):
    class Meta:
        model = PackerImageBuild
        fields: tuple[str, ...] = ()


class PackerPluginSettingsForm(NetBoxModelForm):
    class Meta:
        model = PackerPluginSettings
        fields: tuple[str, ...] = ()
