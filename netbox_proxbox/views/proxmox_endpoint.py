
from netbox.views import generic

from netbox_proxbox import filtersets, forms, models, tables

class ProxmoxEndpointView(generic.ObjectView):
    queryset = models.ProxmoxEndpoint.objects.all()


class ProxmoxEndpointListView(generic.ObjectListView):
    queryset = models.ProxmoxEndpoint.objects.all()
    table = tables.ProxmoxEndpointTable
    filterset = filtersets.ProxmoxEndpointFilterSet
    filterset_form = forms.ProxmoxEndpointFilterForm

    
class ProxmoxEndpointEditView(generic.ObjectEditView):
    queryset = models.ProxmoxEndpoint.objects.all()
    form = forms.ProxmoxEndpointForm


class ProxmoxEndpointDeleteView(generic.ObjectDeleteView):
    queryset = models.ProxmoxEndpoint.objects.all()