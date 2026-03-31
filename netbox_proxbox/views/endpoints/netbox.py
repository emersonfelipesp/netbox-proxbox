"""Provide NetBox CRUD views for remote NetBox endpoint records."""

from netbox.views import generic
from utilities.views import register_model_view

from netbox_proxbox.filtersets import NetBoxEndpointFilterSet
from netbox_proxbox.forms import NetBoxEndpointFilterForm, NetBoxEndpointForm
from netbox_proxbox.models import NetBoxEndpoint
from netbox_proxbox.tables import NetBoxEndpointTable


__all__ = (
    "NetBoxEndpointView",
    "NetBoxEndpointListView",
    "NetBoxEndpointEditView",
    "NetBoxEndpointDeleteView",
)


@register_model_view(NetBoxEndpoint)
class NetBoxEndpointView(generic.ObjectView):
    """Detail view for a remote NetBox API endpoint configuration."""

    queryset = NetBoxEndpoint.objects.all()


@register_model_view(NetBoxEndpoint, "list", path="", detail=False)
class NetBoxEndpointListView(generic.ObjectListView):
    """Filterable list of NetBox endpoint records."""

    queryset = NetBoxEndpoint.objects.all()
    table = NetBoxEndpointTable
    filterset = NetBoxEndpointFilterSet
    filterset_form = NetBoxEndpointFilterForm
    template_name = "netbox_proxbox/netboxendpoint_list.html"


@register_model_view(NetBoxEndpoint, "add", detail=False)
@register_model_view(NetBoxEndpoint, "edit")
class NetBoxEndpointEditView(generic.ObjectEditView):
    """Create or edit a NetBox endpoint (token and URL settings)."""

    queryset = NetBoxEndpoint.objects.all()
    form = NetBoxEndpointForm


@register_model_view(NetBoxEndpoint, "delete")
class NetBoxEndpointDeleteView(generic.ObjectDeleteView):
    """Delete a NetBox endpoint record."""

    queryset = NetBoxEndpoint.objects.all()
