from django.db.models import Q
from netbox.filtersets import NetBoxModelFilterSet
from .models import ProxmoxEndpoint

class ProxmoxEndpointFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = ProxmoxEndpoint
        fields = ['name', 'ip_address', 'port', 'username', 'verify_ssl']
    
    def search(self, queryset, name, value):
        """Perform the filtered search."""
        if not value.strip():
            return queryset
        qs_filter = (
                Q(value__icontains=value)
                | Q(description__icontains=value)
        )
        return queryset.filter(qs_filter)