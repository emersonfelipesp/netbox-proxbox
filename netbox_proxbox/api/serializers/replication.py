"""API serializer for Replication records synced from Proxmox."""

from __future__ import annotations

from netbox.api.fields import ChoiceField
from netbox.api.serializers import NetBoxModelSerializer
from rest_framework import serializers
from virtualization.api.serializers_.nested import NestedVirtualMachineSerializer

from netbox_proxbox.api.serializers.cluster import (
    NestedProxmoxEndpointSerializer,
    NestedProxmoxNodeSerializer,
)
from netbox_proxbox.choices import (
    ReplicationJobTypeChoices,
    ReplicationRemoveJobChoices,
    ReplicationStatusChoices,
)
from netbox_proxbox.models import Replication


class ReplicationSerializer(NetBoxModelSerializer):
    """Full representation of a Proxmox Replication stored in NetBox."""

    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:replication-detail",
    )
    endpoint = NestedProxmoxEndpointSerializer(required=False, allow_null=True)
    virtual_machine = NestedVirtualMachineSerializer()
    proxmox_node = NestedProxmoxNodeSerializer(required=False, allow_null=True)
    job_type = ChoiceField(choices=ReplicationJobTypeChoices, required=False)
    remove_job = ChoiceField(
        choices=ReplicationRemoveJobChoices,
        required=False,
        allow_null=True,
        allow_blank=True,
    )
    status = ChoiceField(choices=ReplicationStatusChoices, required=False)

    class Meta:
        model = Replication
        fields = (
            "id",
            "url",
            "display",
            "endpoint",
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
            "status",
            "raw_config",
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
            "status",
        )
