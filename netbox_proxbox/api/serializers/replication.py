"""API serializer for Replication records synced from Proxmox."""

from __future__ import annotations

from netbox.api.fields import ChoiceField
from netbox.api.serializers import NetBoxModelSerializer
from rest_framework import serializers
from virtualization.api.serializers_.nested import NestedVirtualMachineSerializer

from netbox_proxbox.api.serializers.cluster import NestedProxmoxNodeSerializer
from netbox_proxbox.models import Replication


class ReplicationSerializer(NetBoxModelSerializer):
    """Full representation of a Proxmox Replication stored in NetBox."""

    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:replication-detail",
    )
    virtual_machine = NestedVirtualMachineSerializer()
    proxmox_node = NestedProxmoxNodeSerializer(required=False, allow_null=True)
    job_type = ChoiceField(choices=[("local", "Local")], required=False)
    remove_job = ChoiceField(
        choices=[("local", "Local"), ("full", "Full")],
        required=False,
        allow_null=True,
        allow_blank=True,
    )

    class Meta:
        model = Replication
        fields = (
            "id",
            "url",
            "display",
            "replication_id",
            "virtual_machine",
            "proxmox_node",
            "guest",
            "target",
            "job_type",
            "schedule",
            "rate",
            "comment",
            "disable",
            "source",
            "jobnum",
            "remove_job",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = (
            "id",
            "url",
            "display",
            "replication_id",
            "virtual_machine",
            "target",
        )
