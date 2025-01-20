# NetBox Imports
from netbox.views import generic

# ProxBox Imports
from netbox_proxbox.models import FastAPIEndpoint
from netbox_proxbox.tables import FastAPIEndpointTable
from netbox_proxbox.filtersets import FastAPIEndpointFilterSet
from netbox_proxbox.forms import FastAPIEndpointForm, FastAPIEndpointFilterForm


__all__ = (
    'FastAPIEndpointView',
    'FastAPIEndpointListView',
    'FastAPIEndpointEditView',
    'FastAPIEndpointDeleteView',
)


class FastAPIEndpointView(generic.ObjectView):
    queryset = FastAPIEndpoint.objects.all()


class FastAPIEndpointListView(generic.ObjectListView):
    queryset = FastAPIEndpoint.objects.all()
    table = FastAPIEndpointTable
    filterset = FastAPIEndpointFilterSet
    filterset_form = FastAPIEndpointFilterForm


class FastAPIEndpointEditView(generic.ObjectEditView):
    queryset = FastAPIEndpoint.objects.all()
    form = FastAPIEndpointForm


class FastAPIEndpointDeleteView(generic.ObjectDeleteView):
    queryset = FastAPIEndpoint.objects.all()