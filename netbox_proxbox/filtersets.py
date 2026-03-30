"""Define NetBox filtersets for the plugin's list views and API queries."""

from django.db.models import Q

from netbox.filtersets import NetBoxModelFilterSet
from utilities.filtersets import register_filterset

from .models import (
    FastAPIEndpoint,
    NetBoxEndpoint,
    ProxmoxEndpoint,
    SyncProcess,
    VMBackup,
    VMSnapshot,
)


@register_filterset
class SyncProcessFilterSet(NetBoxModelFilterSet):
    """Filter and search background sync process records."""

    class Meta:
        model = SyncProcess
        fields = (
            "id",
            "name",
            "sync_type",
            "status",
            "started_at",
            "completed_at",
            "runtime",
        )

    def search(self, queryset, name, value):
        """Match the search term against sync process names (case-insensitive)."""
        if not value.strip():
            return queryset
        return queryset.filter(Q(name__icontains=value))


@register_filterset
class ProxmoxEndpointFilterSet(NetBoxModelFilterSet):
    """Filter Proxmox VE endpoint records for list and API views."""

    class Meta:
        model = ProxmoxEndpoint
        fields = ("id", "name", "domain", "ip_address", "mode")

    def search(self, queryset, name, value):
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

    def search(self, queryset, name, value):
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

    def search(self, queryset, name, value):
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

    def search(self, queryset, name, value):
        """Match VM name, storage, or volume id (case-insensitive)."""
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(virtual_machine__name__icontains=value)
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
            "virtual_machine",
            "subtype",
            "status",
            "name",
            "vmid",
            "node",
            "parent",
            "snaptime",
        )

    def search(self, queryset, name, value):
        """Match VM name, snapshot name, node, or description."""
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(virtual_machine__name__icontains=value)
            | Q(name__icontains=value)
            | Q(node__icontains=value)
            | Q(description__icontains=value)
        )
