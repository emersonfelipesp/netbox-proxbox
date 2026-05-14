"""django-tables2 layouts for netbox-ceph list views."""

from __future__ import annotations

import django_tables2 as tables
from netbox.tables import NetBoxTable
from netbox.tables.columns import BooleanColumn

from netbox_ceph.models import (
    CephCluster,
    CephCrushRule,
    CephDaemon,
    CephFilesystem,
    CephFlag,
    CephHealthCheck,
    CephOSD,
    CephPool,
)


class CephClusterTable(NetBoxTable):
    name = tables.Column(linkify=True)
    endpoint = tables.Column(linkify=True)
    proxmox_cluster = tables.Column(linkify=True)

    class Meta(NetBoxTable.Meta):
        model = CephCluster
        fields = (
            "pk",
            "id",
            "name",
            "endpoint",
            "proxmox_cluster",
            "fsid",
            "health",
            "last_seen_at",
            "actions",
        )
        default_columns = ("name", "endpoint", "proxmox_cluster", "fsid", "health", "last_seen_at")


class CephDaemonTable(NetBoxTable):
    name = tables.Column(linkify=True)
    endpoint = tables.Column(linkify=True)
    cluster = tables.Column(linkify=True)
    proxmox_node = tables.Column(linkify=True)

    class Meta(NetBoxTable.Meta):
        model = CephDaemon
        fields = (
            "pk",
            "id",
            "daemon_type",
            "name",
            "daemon_id",
            "endpoint",
            "cluster",
            "proxmox_node",
            "host",
            "state",
            "version",
            "last_seen_at",
            "actions",
        )
        default_columns = (
            "daemon_type",
            "name",
            "endpoint",
            "cluster",
            "host",
            "state",
            "last_seen_at",
        )


class CephOSDTable(NetBoxTable):
    osd_id = tables.Column(linkify=True, verbose_name="OSD")
    endpoint = tables.Column(linkify=True)
    cluster = tables.Column(linkify=True)
    proxmox_node = tables.Column(linkify=True)
    up = BooleanColumn()
    in_cluster = BooleanColumn()

    class Meta(NetBoxTable.Meta):
        model = CephOSD
        fields = (
            "pk",
            "id",
            "osd_id",
            "endpoint",
            "cluster",
            "proxmox_node",
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
            "last_seen_at",
            "actions",
        )
        default_columns = (
            "osd_id",
            "endpoint",
            "cluster",
            "host",
            "up",
            "in_cluster",
            "device_class",
            "weight",
            "last_seen_at",
        )


class CephPoolTable(NetBoxTable):
    name = tables.Column(linkify=True)
    endpoint = tables.Column(linkify=True)
    cluster = tables.Column(linkify=True)

    class Meta(NetBoxTable.Meta):
        model = CephPool
        fields = (
            "pk",
            "id",
            "name",
            "endpoint",
            "cluster",
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
            "last_seen_at",
            "actions",
        )
        default_columns = (
            "name",
            "endpoint",
            "cluster",
            "size",
            "min_size",
            "application",
            "percent_used",
            "last_seen_at",
        )


class CephFilesystemTable(NetBoxTable):
    name = tables.Column(linkify=True)
    endpoint = tables.Column(linkify=True)
    cluster = tables.Column(linkify=True)
    metadata_pool = tables.Column(linkify=True)

    class Meta(NetBoxTable.Meta):
        model = CephFilesystem
        fields = (
            "pk",
            "id",
            "name",
            "endpoint",
            "cluster",
            "metadata_pool",
            "standby_count_wanted",
            "last_seen_at",
            "actions",
        )
        default_columns = ("name", "endpoint", "cluster", "metadata_pool", "last_seen_at")


class CephCrushRuleTable(NetBoxTable):
    name = tables.Column(linkify=True)
    endpoint = tables.Column(linkify=True)
    cluster = tables.Column(linkify=True)

    class Meta(NetBoxTable.Meta):
        model = CephCrushRule
        fields = (
            "pk",
            "id",
            "name",
            "endpoint",
            "cluster",
            "rule_id",
            "rule_type",
            "device_class",
            "last_seen_at",
            "actions",
        )
        default_columns = (
            "name",
            "endpoint",
            "cluster",
            "rule_type",
            "device_class",
            "last_seen_at",
        )


class CephFlagTable(NetBoxTable):
    name = tables.Column(linkify=True)
    endpoint = tables.Column(linkify=True)
    cluster = tables.Column(linkify=True)
    enabled = BooleanColumn()

    class Meta(NetBoxTable.Meta):
        model = CephFlag
        fields = (
            "pk",
            "id",
            "name",
            "endpoint",
            "cluster",
            "enabled",
            "value",
            "last_seen_at",
            "actions",
        )
        default_columns = ("name", "endpoint", "cluster", "enabled", "value", "last_seen_at")


class CephHealthCheckTable(NetBoxTable):
    name = tables.Column(linkify=True)
    endpoint = tables.Column(linkify=True)
    cluster = tables.Column(linkify=True)

    class Meta(NetBoxTable.Meta):
        model = CephHealthCheck
        fields = (
            "pk",
            "id",
            "name",
            "endpoint",
            "cluster",
            "severity",
            "summary",
            "source",
            "first_seen_at",
            "last_seen_at",
            "actions",
        )
        default_columns = ("name", "endpoint", "cluster", "severity", "summary", "last_seen_at")
