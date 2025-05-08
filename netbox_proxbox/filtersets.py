from django.db.models import Q
from netbox.filtersets import NetBoxModelFilterSet
from .models import ProxmoxEndpoint, NetBoxEndpoint, FastAPIEndpoint, SyncProcess, VMBackup


class SyncProcessFilterSet(NetBoxModelFilterSet):
    """
    FilterSet for SyncProcess model.
    It is used in the SyncProcessListView.
    """
    class Meta:
        model = SyncProcess
        fields = ['id', 'name', 'sync_type', 'status', 'started_at', 'completed_at', 'runtime']

    def search(self, queryset, name, value):
        return queryset.filter(name__icontains=value)


class ProxmoxEndpointFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = ProxmoxEndpoint
        fields = ['id', 'name', 'domain', 'ip_address', 'mode']
    
    def search(self, queryset, name, value):
            return queryset.filter(name__icontains=value)


class NetBoxEndpointFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = NetBoxEndpoint
        fields = ['id', 'name', 'domain', 'ip_address']

    def search(self, queryset, name, value):
        return queryset.filter(name__icontains=value)


class FastAPIEndpointFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = FastAPIEndpoint
        fields = ['id', 'name', 'domain', 'ip_address']
    
    def search(self, queryset, name, value):
        return queryset.filter(name__icontains=value)


class VMBackupFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = VMBackup
        fields = ['id', 'virtual_machine', 'subtype', 'format', 'creation_time', 'size', 'used', 'encrypted', 'volume_id', 'vmid']

    def search(self, queryset, name, value):
        return queryset.filter(virtual_machine__name__icontains=value)