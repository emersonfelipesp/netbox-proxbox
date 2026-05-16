"""DRF serializers for PBS inventory models."""

from __future__ import annotations

from netbox.api.serializers import NetBoxModelSerializer
from rest_framework import serializers

from netbox_pbs.models import (
    PBSDatastore,
    PBSJob,
    PBSPluginSettings,
    PBSServer,
    PBSSnapshot,
)


class PBSPluginSettingsSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_pbs-api:pbspluginsettings-detail"
    )

    class Meta:
        model = PBSPluginSettings
        fields = (
            "id",
            "url",
            "display",
            "proxbox_api_url",
            "proxbox_api_key",
            "branching_enabled",
            "branch_name_prefix",
            "branch_on_conflict",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display")


class PBSServerSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_pbs-api:pbsserver-detail"
    )

    class Meta:
        model = PBSServer
        fields = (
            "id",
            "url",
            "display",
            "name",
            "host",
            "port",
            "token_id",
            "fingerprint",
            "verify_ssl",
            "status",
            "version",
            "last_seen_at",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "name", "host", "status")


class PBSDatastoreSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_pbs-api:pbsdatastore-detail"
    )

    class Meta:
        model = PBSDatastore
        fields = (
            "id",
            "url",
            "display",
            "server",
            "name",
            "path",
            "used_bytes",
            "total_bytes",
            "avail_bytes",
            "gc_status",
            "comment",
            "last_seen_at",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "name", "server", "gc_status")


class PBSSnapshotSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_pbs-api:pbssnapshot-detail"
    )

    class Meta:
        model = PBSSnapshot
        fields = (
            "id",
            "url",
            "display",
            "server",
            "datastore_name",
            "backup_type",
            "backup_id",
            "backup_time",
            "size_bytes",
            "owner",
            "protected",
            "comment",
            "verification_state",
            "last_seen_at",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "backup_type", "backup_id")


class PBSJobSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_pbs-api:pbsjob-detail"
    )

    class Meta:
        model = PBSJob
        fields = (
            "id",
            "url",
            "display",
            "server",
            "job_type",
            "job_id",
            "store",
            "schedule",
            "comment",
            "disable",
            "last_run_state",
            "last_run_endtime",
            "next_run",
            "last_seen_at",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "job_type", "job_id", "last_run_state")
