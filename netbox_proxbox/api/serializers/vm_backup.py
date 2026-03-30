"""API serializer for VM backup records synced from Proxmox."""

from __future__ import annotations

from netbox.api.fields import ChoiceField
from netbox.api.serializers import NetBoxModelSerializer
from rest_framework import serializers
from virtualization.api.serializers_.nested import NestedVirtualMachineSerializer

from netbox_proxbox.choices import (
    ProxmoxBackupFormatChoices,
    ProxmoxBackupSubtypeChoices,
)
from netbox_proxbox.models import VMBackup


class VMBackupSerializer(NetBoxModelSerializer):
    """Full representation of a Proxmox VM backup stored in NetBox."""

    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:vmbackup-detail",
    )
    virtual_machine = NestedVirtualMachineSerializer()
    subtype = ChoiceField(choices=ProxmoxBackupSubtypeChoices)
    format = ChoiceField(choices=ProxmoxBackupFormatChoices)

    class Meta:
        model = VMBackup
        fields = (
            "id",
            "url",
            "display",
            "virtual_machine",
            "storage",
            "subtype",
            "format",
            "creation_time",
            "size",
            "notes",
            "volume_id",
            "vmid",
            "used",
            "encrypted",
            "verification_state",
            "verification_upid",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "storage", "creation_time")
