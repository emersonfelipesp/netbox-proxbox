# NetBox Imports
from netbox.views import generic

# ProxBox Imports
from netbox_proxbox.models import NetBoxEndpoint
from netbox_proxbox.tables import NetBoxEndpointTable
from netbox_proxbox.filtersets import NetBoxEndpointFilterSet
from netbox_proxbox.forms import NetBoxEndpointForm, NetBoxEndpointFilterForm


__all__ = (
    'NetBoxEndpointView',
    'NetBoxEndpointListView',
    'NetBoxEndpointEditView',
    'NetBoxEndpointDeleteView',
)


class NetBoxEndpointView(generic.ObjectView):
    queryset = NetBoxEndpoint.objects.all()


class NetBoxEndpointListView(generic.ObjectListView):
    queryset = NetBoxEndpoint.objects.all()
    table = NetBoxEndpointTable
    filterset = NetBoxEndpointFilterSet
    filterset_form = NetBoxEndpointFilterForm


class NetBoxEndpointEditView(generic.ObjectEditView):
    queryset = NetBoxEndpoint.objects.all()
    form = NetBoxEndpointForm


class NetBoxEndpointDeleteView(generic.ObjectDeleteView):
    queryset = NetBoxEndpoint.objects.all()