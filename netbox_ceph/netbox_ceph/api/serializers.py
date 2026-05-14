"""DRF serializers for read-only Ceph inventory models."""

from __future__ import annotations

from netbox.api.serializers import NetBoxModelSerializer
from rest_framework import serializers

from netbox_ceph.models import (
    CephCluster,
    CephCrushRule,
    CephDaemon,
    CephFilesystem,
    CephFlag,
    CephHealthCheck,
    CephOSD,
    CephPluginSettings,
    CephPool,
)


class CephPluginSettingsSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_ceph-api:cephpluginsettings-detail"
    )

    class Meta:
        model = CephPluginSettings
        fields = (
            "id",
            "url",
            "display",
            "branching_enabled",
            "branch_name_prefix",
            "branch_on_conflict",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display")


class CephClusterSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_ceph-api:cephcluster-detail"
    )

    class Meta:
        model = CephCluster
        fields = (
            "id",
            "url",
            "display",
            "endpoint",
            "proxmox_cluster",
            "name",
            "fsid",
            "health",
            "quorum_names",
            "status",
            "last_seen_at",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "name", "health")


class CephDaemonSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_ceph-api:cephdaemon-detail"
    )

    class Meta:
        model = CephDaemon
        fields = (
            "id",
            "url",
            "display",
            "endpoint",
            "cluster",
            "proxmox_node",
            "daemon_type",
            "name",
            "daemon_id",
            "host",
            "state",
            "status",
            "version",
            "metadata",
            "last_seen_at",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "daemon_type", "name", "state")


class CephOSDSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_ceph-api:cephosd-detail"
    )

    class Meta:
        model = CephOSD
        fields = (
            "id",
            "url",
            "display",
            "endpoint",
            "cluster",
            "proxmox_node",
            "osd_id",
            "name",
            "host",
            "up",
            "in_cluster",
            "status",
            "device_class",
            "weight",
            "reweight",
            "used_bytes",
            "available_bytes",
            "total_bytes",
            "pgs",
            "metadata",
            "last_seen_at",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "osd_id", "up", "in_cluster")


class CephPoolSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_ceph-api:cephpool-detail"
    )

    class Meta:
        model = CephPool
        fields = (
            "id",
            "url",
            "display",
            "endpoint",
            "cluster",
            "name",
            "pool_id",
            "size",
            "min_size",
            "pg_num",
            "pg_autoscale_mode",
            "crush_rule",
            "application",
            "used_bytes",
            "max_available_bytes",
            "percent_used",
            "status",
            "last_seen_at",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "name")


class CephFilesystemSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_ceph-api:cephfilesystem-detail"
    )

    class Meta:
        model = CephFilesystem
        fields = (
            "id",
            "url",
            "display",
            "endpoint",
            "cluster",
            "name",
            "metadata_pool",
            "data_pools",
            "standby_count_wanted",
            "status",
            "last_seen_at",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "name")


class CephCrushRuleSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_ceph-api:cephcrushrule-detail"
    )

    class Meta:
        model = CephCrushRule
        fields = (
            "id",
            "url",
            "display",
            "endpoint",
            "cluster",
            "name",
            "rule_id",
            "rule_type",
            "device_class",
            "steps",
            "raw",
            "last_seen_at",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "name", "rule_type")


class CephFlagSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_ceph-api:cephflag-detail"
    )

    class Meta:
        model = CephFlag
        fields = (
            "id",
            "url",
            "display",
            "endpoint",
            "cluster",
            "name",
            "enabled",
            "value",
            "raw",
            "last_seen_at",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "name", "enabled")


class CephHealthCheckSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_ceph-api:cephhealthcheck-detail"
    )

    class Meta:
        model = CephHealthCheck
        fields = (
            "id",
            "url",
            "display",
            "endpoint",
            "cluster",
            "name",
            "severity",
            "summary",
            "detail",
            "source",
            "first_seen_at",
            "last_seen_at",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "name", "severity")
