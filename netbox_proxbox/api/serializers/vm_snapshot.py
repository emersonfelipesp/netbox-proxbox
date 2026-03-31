"""API serializer for VM snapshot records synced from Proxmox."""

from __future__ import annotations

from netbox.api.fields import ChoiceField
from netbox.api.serializers import NetBoxModelSerializer
from rest_framework import serializers
from virtualization.api.serializers_.nested import NestedVirtualMachineSerializer

from netbox_proxbox.choices import (
    ProxmoxSnapshotStatusChoices,
    ProxmoxSnapshotSubtypeChoices,
)
from netbox_proxbox.models import VMSnapshot


class VMSnapshotSerializer(NetBoxModelSerializer):
    """Full representation of a Proxmox VM snapshot stored in NetBox."""

    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:vmsnapshot-detail",
    )
    virtual_machine = NestedVirtualMachineSerializer()
    subtype = ChoiceField(choices=ProxmoxSnapshotSubtypeChoices)
    status = ChoiceField(choices=ProxmoxSnapshotStatusChoices)

    class Meta:
        model = VMSnapshot
        fields = (
            "id",
            "url",
            "display",
            "virtual_machine",
            "storage",
            "name",
            "description",
            "vmid",
            "node",
            "snaptime",
            "parent",
            "subtype",
            "status",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = (
            "id",
            "url",
            "display",
            "name",
            "virtual_machine",
            "storage",
            "status",
        )
