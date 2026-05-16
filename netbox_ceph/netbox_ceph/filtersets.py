"""NetBox filtersets for netbox-ceph list views and (future) API queries.

Filtersets are intentionally narrow: in v1 the netbox-ceph plugin only
reflects Proxmox-managed Ceph state, so all queries are read-only.
"""

from __future__ import annotations

from django.db.models import Q
from netbox.filtersets import NetBoxModelFilterSet

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


class _EndpointSearchMixin:
    """Shared free-text search across name/endpoint name."""

    def search(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(Q(name__icontains=value) | Q(endpoint__name__icontains=value))


class CephClusterFilterSet(_EndpointSearchMixin, NetBoxModelFilterSet):
    class Meta:
        model = CephCluster
        fields = ("id", "endpoint", "proxmox_cluster", "name", "fsid", "health")


class CephDaemonFilterSet(_EndpointSearchMixin, NetBoxModelFilterSet):
    class Meta:
        model = CephDaemon
        fields = (
            "id",
            "endpoint",
            "cluster",
            "proxmox_node",
            "daemon_type",
            "name",
            "daemon_id",
            "state",
        )


class CephOSDFilterSet(_EndpointSearchMixin, NetBoxModelFilterSet):
    class Meta:
        model = CephOSD
        fields = (
            "id",
            "endpoint",
            "cluster",
            "proxmox_node",
            "osd_id",
            "up",
            "in_cluster",
            "device_class",
        )

    def search(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(
            Q(name__icontains=value) | Q(host__icontains=value) | Q(endpoint__name__icontains=value)
        )


class CephPoolFilterSet(_EndpointSearchMixin, NetBoxModelFilterSet):
    class Meta:
        model = CephPool
        fields = ("id", "endpoint", "cluster", "name", "pool_id", "application")


class CephFilesystemFilterSet(_EndpointSearchMixin, NetBoxModelFilterSet):
    class Meta:
        model = CephFilesystem
        fields = ("id", "endpoint", "cluster", "name")


class CephCrushRuleFilterSet(_EndpointSearchMixin, NetBoxModelFilterSet):
    class Meta:
        model = CephCrushRule
        fields = ("id", "endpoint", "cluster", "name", "rule_id", "rule_type", "device_class")


class CephFlagFilterSet(_EndpointSearchMixin, NetBoxModelFilterSet):
    class Meta:
        model = CephFlag
        fields = ("id", "endpoint", "cluster", "name", "enabled")


class CephHealthCheckFilterSet(_EndpointSearchMixin, NetBoxModelFilterSet):
    class Meta:
        model = CephHealthCheck
        fields = ("id", "endpoint", "cluster", "name", "severity", "source")
