"""API serializer for VM task history records synced from Proxmox."""

from __future__ import annotations

from netbox.api.serializers import NetBoxModelSerializer
from rest_framework import serializers
from virtualization.api.serializers_.nested import NestedVirtualMachineSerializer

from netbox_proxbox.models import VMTaskHistory


class VMTaskHistorySerializer(NetBoxModelSerializer):
    """Full representation of a Proxmox VM task history record."""

    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:vmtaskhistory-detail",
    )
    virtual_machine = NestedVirtualMachineSerializer()

    class Meta:
        model = VMTaskHistory
        fields = (
            "id",
            "url",
            "display",
            "virtual_machine",
            "vm_type",
            "upid",
            "node",
            "pid",
            "pstart",
            "task_id",
            "task_type",
            "username",
            "start_time",
            "end_time",
            "description",
            "status",
            "task_state",
            "exitstatus",
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
            "start_time",
            "end_time",
            "username",
            "status",
        )
