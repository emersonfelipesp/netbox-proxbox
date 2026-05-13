"""DRF serializers for the netbox-pbs plugin API.

One ``NetBoxModelSerializer`` per persisted PBS model. ``PBSEndpoint`` is the
only writable surface; ``token_value`` is marked write-only so it never
appears in API responses. The five reflected models (``PBSNode``,
``PBSDatastore``, ``PBSBackupGroup``, ``PBSSnapshot``, ``PBSJobStatus``)
serialize their full payload because the read-only enforcement happens at the
viewset layer (``http_method_names`` restricts to GET/HEAD/OPTIONS).
"""

from __future__ import annotations

from netbox.api.fields import ChoiceField
from netbox.api.serializers import NetBoxModelSerializer, WritableNestedSerializer
from rest_framework import serializers

from netbox_pbs.choices import (
    PBSBackupTypeChoices,
    PBSDatastoreGCStatusChoices,
    PBSJobRunStateChoices,
    PBSJobTypeChoices,
    PBSSnapshotVerifyChoices,
)
from netbox_pbs.models import (
    PBSBackupGroup,
    PBSDatastore,
    PBSEndpoint,
    PBSJobStatus,
    PBSNode,
    PBSSnapshot,
)


class NestedPBSEndpointSerializer(WritableNestedSerializer):
    """Minimal PBSEndpoint for nested references."""

    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_pbs-api:pbsendpoint-detail",
    )

    class Meta:
        model = PBSEndpoint
        fields = ["id", "url", "display", "name"]
        brief_fields = ("id", "url", "display", "name")


class NestedPBSDatastoreSerializer(WritableNestedSerializer):
    """Minimal PBSDatastore for nested references."""

    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_pbs-api:pbsdatastore-detail",
    )

    class Meta:
        model = PBSDatastore
        fields = ["id", "url", "display", "name"]
        brief_fields = ("id", "url", "display", "name")


class NestedPBSBackupGroupSerializer(WritableNestedSerializer):
    """Minimal PBSBackupGroup for nested references."""

    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_pbs-api:pbsbackupgroup-detail",
    )

    class Meta:
        model = PBSBackupGroup
        fields = ["id", "url", "display", "backup_type", "backup_id"]
        brief_fields = ("id", "url", "display", "backup_type", "backup_id")


class PBSEndpointSerializer(NetBoxModelSerializer):
    """Full PBSEndpoint serializer. ``token_value`` is write-only."""

    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_pbs-api:pbsendpoint-detail",
    )
    token_value = serializers.CharField(write_only=True)

    class Meta:
        model = PBSEndpoint
        fields = (
            "id",
            "url",
            "display",
            "name",
            "host",
            "port",
            "token_id",
            "token_value",
            "fingerprint",
            "verify_ssl",
            "timeout",
            "last_seen_at",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "name", "host", "port")


class PBSNodeSerializer(NetBoxModelSerializer):
    """Full PBSNode serializer (reflected, read-only at view layer)."""

    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_pbs-api:pbsnode-detail",
    )
    endpoint = NestedPBSEndpointSerializer()

    class Meta:
        model = PBSNode
        fields = (
            "id",
            "url",
            "display",
            "endpoint",
            "hostname",
            "version",
            "uptime_seconds",
            "cpu_pct",
            "memory_used",
            "memory_total",
            "last_seen_at",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "hostname")


class PBSDatastoreSerializer(NetBoxModelSerializer):
    """Full PBSDatastore serializer (reflected, read-only at view layer)."""

    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_pbs-api:pbsdatastore-detail",
    )
    endpoint = NestedPBSEndpointSerializer()
    gc_status = ChoiceField(choices=PBSDatastoreGCStatusChoices)

    class Meta:
        model = PBSDatastore
        fields = (
            "id",
            "url",
            "display",
            "endpoint",
            "name",
            "path",
            "total_bytes",
            "used_bytes",
            "available_bytes",
            "gc_status",
            "last_gc_at",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "name")


class PBSBackupGroupSerializer(NetBoxModelSerializer):
    """Full PBSBackupGroup serializer (reflected, read-only at view layer)."""

    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_pbs-api:pbsbackupgroup-detail",
    )
    datastore = NestedPBSDatastoreSerializer()
    backup_type = ChoiceField(choices=PBSBackupTypeChoices)

    class Meta:
        model = PBSBackupGroup
        fields = (
            "id",
            "url",
            "display",
            "datastore",
            "backup_type",
            "backup_id",
            "owner",
            "comment",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "backup_type", "backup_id")


class PBSSnapshotSerializer(NetBoxModelSerializer):
    """Full PBSSnapshot serializer (reflected, read-only at view layer)."""

    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_pbs-api:pbssnapshot-detail",
    )
    backup_group = NestedPBSBackupGroupSerializer()
    verified = ChoiceField(choices=PBSSnapshotVerifyChoices)

    class Meta:
        model = PBSSnapshot
        fields = (
            "id",
            "url",
            "display",
            "backup_group",
            "backup_time",
            "size_bytes",
            "encrypted",
            "verified",
            "protected",
            "comment",
            "files",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "backup_time")


class PBSJobStatusSerializer(NetBoxModelSerializer):
    """Full PBSJobStatus serializer (reflected, read-only at view layer)."""

    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_pbs-api:pbsjobstatus-detail",
    )
    endpoint = NestedPBSEndpointSerializer()
    datastore = NestedPBSDatastoreSerializer(required=False, allow_null=True)
    job_type = ChoiceField(choices=PBSJobTypeChoices)
    last_run_state = ChoiceField(choices=PBSJobRunStateChoices)

    class Meta:
        model = PBSJobStatus
        fields = (
            "id",
            "url",
            "display",
            "endpoint",
            "datastore",
            "job_type",
            "job_id",
            "enabled",
            "last_run_at",
            "last_run_state",
            "last_run_duration_seconds",
            "next_run_at",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "job_type", "job_id")
