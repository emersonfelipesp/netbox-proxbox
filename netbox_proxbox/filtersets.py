"""Define NetBox filtersets for the plugin's list views and API queries."""

from django.db.models import Q
from netbox.filtersets import NetBoxModelFilterSet
from utilities.filtersets import register_filterset

from .models import (
    BackupRoutine,
    FastAPIEndpoint,
    NetBoxEndpoint,
    ProxmoxCluster,
    ProxmoxEndpoint,
    ProxmoxNode,
    ProxmoxStorage,
    Replication,
    VMBackup,
    VMSnapshot,
    VMTaskHistory,
)


@register_filterset
class ProxmoxEndpointFilterSet(NetBoxModelFilterSet):
    """Filter Proxmox VE endpoint records for list and API views."""

    class Meta:
        model = ProxmoxEndpoint
        fields = ("id", "name", "domain", "ip_address", "mode")

    def search(self, queryset: object, name: str, value: str) -> object:
        """Match the search term against endpoint name or domain."""
        if not value.strip():
            return queryset
        return queryset.filter(Q(name__icontains=value) | Q(domain__icontains=value))


@register_filterset
class NetBoxEndpointFilterSet(NetBoxModelFilterSet):
    """Filter remote NetBox API endpoint records."""

    class Meta:
        model = NetBoxEndpoint
        fields = ("id", "name", "domain", "ip_address")

    def search(self, queryset: object, name: str, value: str) -> object:
        """Match the search term against endpoint name or domain."""
        if not value.strip():
            return queryset
        return queryset.filter(Q(name__icontains=value) | Q(domain__icontains=value))


@register_filterset
class FastAPIEndpointFilterSet(NetBoxModelFilterSet):
    """Filter ProxBox FastAPI backend endpoint records."""

    class Meta:
        model = FastAPIEndpoint
        fields = ("id", "name", "domain", "ip_address")

    def search(self, queryset: object, name: str, value: str) -> object:
        """Match the search term against endpoint name or domain."""
        if not value.strip():
            return queryset
        return queryset.filter(Q(name__icontains=value) | Q(domain__icontains=value))


@register_filterset
class VMBackupFilterSet(NetBoxModelFilterSet):
    """Filter VM backup records synced from Proxmox."""

    class Meta:
        model = VMBackup
        fields = (
            "id",
            "proxmox_storage",
            "virtual_machine",
            "subtype",
            "format",
            "creation_time",
            "size",
            "used",
            "encrypted",
            "volume_id",
            "vmid",
        )

    def search(self, queryset: object, name: str, value: str) -> object:
        """Match VM name, storage, or volume id (case-insensitive)."""
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(virtual_machine__name__icontains=value)
            | Q(proxmox_storage__name__icontains=value)
            | Q(storage__icontains=value)
            | Q(volume_id__icontains=value)
        )


@register_filterset
class VMSnapshotFilterSet(NetBoxModelFilterSet):
    """Filter VM snapshot records synced from Proxmox."""

    class Meta:
        model = VMSnapshot
        fields = (
            "id",
            "proxmox_storage",
            "virtual_machine",
            "subtype",
            "status",
            "name",
            "description",
            "vmid",
            "node",
            "parent",
            "snaptime",
        )

    def search(self, queryset: object, name: str, value: str) -> object:
        """Match VM name, snapshot name, node, or description."""
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(virtual_machine__name__icontains=value)
            | Q(proxmox_storage__name__icontains=value)
            | Q(name__icontains=value)
            | Q(node__icontains=value)
            | Q(description__icontains=value)
        )


@register_filterset
class VMTaskHistoryFilterSet(NetBoxModelFilterSet):
    """Filter VM task history records synced from Proxmox."""

    class Meta:
        model = VMTaskHistory
        fields = (
            "id",
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
        )

    def search(self, queryset: object, name: str, value: str) -> object:
        """Match VM name, task metadata, user name, or task result text."""
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(virtual_machine__name__icontains=value)
            | Q(vm_type__icontains=value)
            | Q(upid__icontains=value)
            | Q(node__icontains=value)
            | Q(task_id__icontains=value)
            | Q(task_type__icontains=value)
            | Q(username__icontains=value)
            | Q(description__icontains=value)
            | Q(status__icontains=value)
            | Q(task_state__icontains=value)
            | Q(exitstatus__icontains=value)
        )


@register_filterset
class ProxmoxStorageFilterSet(NetBoxModelFilterSet):
    """Filter Proxmox storage rows synced by the plugin."""

    class Meta:
        model = ProxmoxStorage
        fields = (
            "id",
            "cluster",
            "cluster__name",
            "name",
            "storage_type",
            "content",
            "path",
            "nodes",
            "shared",
            "enabled",
        )

    def search(self, queryset: object, name: str, value: str) -> object:
        """Match storage name, cluster, or storage path."""
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(name__icontains=value)
            | Q(cluster__name__icontains=value)
            | Q(path__icontains=value)
        )


@register_filterset
class ProxmoxClusterFilterSet(NetBoxModelFilterSet):
    """Filter Proxmox cluster records tracked by the plugin."""

    class Meta:
        model = ProxmoxCluster
        fields = ("id", "endpoint", "netbox_cluster", "name", "mode", "quorate")

    def search(self, queryset: object, name: str, value: str) -> object:
        """Match cluster name or cluster ID."""
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(name__icontains=value) | Q(cluster_id__icontains=value)
        )


@register_filterset
class ProxmoxNodeFilterSet(NetBoxModelFilterSet):
    """Filter Proxmox node records tracked by the plugin."""

    class Meta:
        model = ProxmoxNode
        fields = (
            "id",
            "endpoint",
            "proxmox_cluster",
            "netbox_device",
            "name",
            "ip_address",
            "online",
            "local",
        )

    def search(self, queryset: object, name: str, value: str) -> object:
        """Match node name, IP address, or SSL fingerprint."""
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(name__icontains=value)
            | Q(ip_address__icontains=value)
            | Q(ssl_fingerprint__icontains=value)
        )


@register_filterset
class BackupRoutineFilterSet(NetBoxModelFilterSet):
    """Filter backup routine records synced from Proxmox."""

    class Meta:
        model = BackupRoutine
        fields = (
            "id",
            "endpoint",
            "job_id",
            "enabled",
            "node",
            "storage",
            "status",
            "keep_last",
            "keep_daily",
            "keep_weekly",
            "keep_monthly",
        )

    def search(self, queryset: object, name: str, value: str) -> object:
        """Match job ID or comment."""
        if not value.strip():
            return queryset
        return queryset.filter(Q(job_id__icontains=value) | Q(comment__icontains=value))


@register_filterset
class ReplicationFilterSet(NetBoxModelFilterSet):
    """Filter Replication records synced from Proxmox."""

    class Meta:
        model = Replication
        fields = (
            "id",
            "replication_id",
            "virtual_machine",
            "proxmox_node",
            "guest",
            "target",
            "job_type",
            "schedule",
            "disable",
            "source",
            "jobnum",
            "remove_job",
        )

    def search(self, queryset: object, name: str, value: str) -> object:
        """Match replication ID, VM name, target, comment, or source."""
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(replication_id__icontains=value)
            | Q(virtual_machine__name__icontains=value)
            | Q(target__icontains=value)
            | Q(comment__icontains=value)
            | Q(source__icontains=value)
        )
