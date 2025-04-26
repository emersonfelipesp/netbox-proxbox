# NetBox Imports
from netbox.views import generic
from utilities.views import register_model_view

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


@register_model_view(ProxmoxEndpoint)
class ProxmoxEndpointView(generic.ObjectView):
    """
    Display a single Proxmox endpoint.
    """
    queryset = ProxmoxEndpoint.objects.all()


@register_model_view(ProxmoxEndpoint, 'list', path='', detail=False)
class ProxmoxEndpointListView(generic.ObjectListView):
    """
    Display a list of Proxmox endpoints.
    """
    queryset = ProxmoxEndpoint.objects.all()
    table = ProxmoxEndpointTable
    filterset = ProxmoxEndpointFilterSet
    filterset_form = ProxmoxEndpointFilterForm


@register_model_view(ProxmoxEndpoint, 'add', detail=False)
@register_model_view(ProxmoxEndpoint, 'edit')
class ProxmoxEndpointEditView(generic.ObjectEditView):
    """
    Add or edit a Proxmox endpoint.
    """
    queryset = ProxmoxEndpoint.objects.all()
    form = ProxmoxEndpointForm


@register_model_view(ProxmoxEndpoint, 'delete')
class ProxmoxEndpointDeleteView(generic.ObjectDeleteView):
    """
    Delete a Proxmox endpoint.
    """
    queryset = ProxmoxEndpoint.objects.all()