"""API serializer for the ProxmoxVMCloudInit model (issue #363)."""

from __future__ import annotations

from netbox.api.serializers import NetBoxModelSerializer
from rest_framework import serializers
from virtualization.api.serializers_.nested import NestedVirtualMachineSerializer

from netbox_proxbox.models import ProxmoxVMCloudInit


class ProxmoxVMCloudInitSerializer(NetBoxModelSerializer):
    """Full representation of a Proxmox VM cloud-init row stored in NetBox.

    proxbox-api writes this resource; the NetBox UI keeps it read-only.
    ``sshkeys`` is delivered already decoded (newlines as ``\\n``); proxbox-api
    runs ``urllib.parse.unquote`` upstream.
    """

    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:proxmoxvmcloudinit-detail",
    )
    virtual_machine = NestedVirtualMachineSerializer()

    class Meta:
        model = ProxmoxVMCloudInit
        fields = (
            "id",
            "url",
            "display",
            "virtual_machine",
            "ciuser",
            "sshkeys",
            "ipconfig0",
            "sshkeys_truncated",
            "last_synced",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = (
            "id",
            "url",
            "display",
            "virtual_machine",
            "ciuser",
        )
