
from netbox.views import generic

from netbox_proxbox.models import (
    ProxmoxEndpoint,
)

from netbox_proxbox import tables, forms

class ProxmoxEndpointView(generic.ObjectView):
    queryset = ProxmoxEndpoint.objects.all()


class ProxmoxEndpointListView(generic.ObjectListView):
    queryset = ProxmoxEndpoint.objects.all()
    table = tables.ProxmoxEndpointTable

    
class ProxmoxEndpointEditView(generic.ObjectEditView):
    queryset = ProxmoxEndpoint.objects.all()
    form = forms.ProxmoxEndpointForm


class ProxmoxEndpointDeleteView(generic.ObjectDeleteView):
    queryset = ProxmoxEndpoint.objects.all()