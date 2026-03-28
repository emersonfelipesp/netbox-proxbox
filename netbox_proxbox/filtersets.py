from django.db.models import Q

from netbox.filtersets import NetBoxModelFilterSet
from utilities.filtersets import register_filterset

from .models import FastAPIEndpoint, NetBoxEndpoint, ProxmoxEndpoint, SyncProcess, VMBackup


@register_filterset
class SyncProcessFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = SyncProcess
        fields = ("id", "name", "sync_type", "status", "started_at", "completed_at", "runtime")

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(Q(name__icontains=value))


@register_filterset
class ProxmoxEndpointFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = ProxmoxEndpoint
        fields = ("id", "name", "domain", "ip_address", "mode")

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(Q(name__icontains=value) | Q(domain__icontains=value))


@register_filterset
class NetBoxEndpointFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = NetBoxEndpoint
        fields = ("id", "name", "domain", "ip_address")

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(Q(name__icontains=value) | Q(domain__icontains=value))


@register_filterset
class FastAPIEndpointFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = FastAPIEndpoint
        fields = ("id", "name", "domain", "ip_address")

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(Q(name__icontains=value) | Q(domain__icontains=value))


@register_filterset
class VMBackupFilterSet(NetBoxModelFilterSet):
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
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(virtual_machine__name__icontains=value)
            | Q(storage__icontains=value)
            | Q(volume_id__icontains=value)
        )
