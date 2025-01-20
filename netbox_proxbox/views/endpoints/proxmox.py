
# NetBox Imports
from netbox.views import generic

# Proxbox Imports
from netbox_proxbox.models import ProxmoxEndpoint
from netbox_proxbox.tables import ProxmoxEndpointTable
from netbox_proxbox.filtersets import ProxmoxEndpointFilterSet
from netbox_proxbox.forms import ProxmoxEndpointForm, ProxmoxEndpointFilterForm


__all__ = (
    'ProxmoxEndpointView',
    'ProxmoxEndpointListView',
    'ProxmoxEndpointEditView',
    'ProxmoxEndpointDeleteView',
)


class ProxmoxEndpointView(generic.ObjectView):
    queryset = ProxmoxEndpoint.objects.all()


class ProxmoxEndpointListView(generic.ObjectListView):
    queryset = ProxmoxEndpoint.objects.all()
    table = ProxmoxEndpointTable
    filterset = ProxmoxEndpointFilterSet
    filterset_form = ProxmoxEndpointFilterForm

    
class ProxmoxEndpointEditView(generic.ObjectEditView):
    queryset = ProxmoxEndpoint.objects.all()
    form = ProxmoxEndpointForm


class ProxmoxEndpointDeleteView(generic.ObjectDeleteView):
    queryset = ProxmoxEndpoint.objects.all()