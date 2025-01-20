from django.db.models import Q
from netbox.filtersets import NetBoxModelFilterSet
from .models import ProxmoxEndpoint, NetBoxEndpoint


class ProxmoxEndpointFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = ProxmoxEndpoint
        fields = ['id', 'name', 'ip_address', 'mode']
    
    def search(self, queryset, name, value):
            return queryset.filter(name__icontains=value)


class NetBoxEndpointFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = NetBoxEndpoint
        fields = ['id', 'name', 'ip_address']

    def search(self, queryset, name, value):
        return queryset.filter(name__icontains=value)
