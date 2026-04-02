"""API serializer for backup routine records synced from Proxmox."""

from __future__ import annotations

from netbox.api.fields import ChoiceField
from netbox.api.serializers import NetBoxModelSerializer
from rest_framework import serializers

from netbox_proxbox.api.serializers.endpoints import NestedProxmoxEndpointSerializer
from netbox_proxbox.api.serializers.storage import NestedProxmoxStorageSerializer
from netbox_proxbox.choices import BackupRoutineStatusChoices
from netbox_proxbox.models import BackupRoutine, ProxmoxNode


class BackupRoutineSerializer(NetBoxModelSerializer):
    """Full representation of a Proxmox backup routine stored in NetBox."""

    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:backuproutine-detail",
    )
    endpoint = NestedProxmoxEndpointSerializer()
    node = serializers.SerializerMethodField()
    storage = NestedProxmoxStorageSerializer(required=False, allow_null=True)
    fleecing_storage = NestedProxmoxStorageSerializer(required=False, allow_null=True)
    status = ChoiceField(
        choices=BackupRoutineStatusChoices, required=False, allow_null=True
    )

    class Meta:
        model = BackupRoutine
        fields = (
            "id",
            "url",
            "display",
            "endpoint",
            "job_id",
            "enabled",
            "schedule",
            "next_run",
            "node",
            "storage",
            "selection",
            "comment",
            "status",
            "keep_last",
            "keep_daily",
            "keep_weekly",
            "keep_monthly",
            "keep_yearly",
            "keep_all",
            "notes_template",
            "bwlimit",
            "zstd",
            "io_workers",
            "fleecing",
            "fleecing_storage",
            "repeat_missed",
            "pbs_change_detection_mode",
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
            "endpoint",
            "job_id",
            "enabled",
            "schedule",
            "next_run",
            "storage",
            "status",
        )

    def get_node(self, obj: BackupRoutine) -> dict | None:
        if obj.node is None:
            return None
        return {
            "id": obj.node.id,
            "url": f"/api/plugins/proxbox/proxmox-nodes/{obj.node.id}/",
            "display": obj.node.name,
        }


class NestedBackupRoutineSerializer(NetBoxModelSerializer):
    """Nested representation of a backup routine for use within other serializers."""

    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:backuproutine-detail",
    )

    class Meta:
        model = BackupRoutine
        fields = (
            "id",
            "url",
            "display",
            "job_id",
            "enabled",
        )
