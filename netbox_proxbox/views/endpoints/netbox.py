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
    queryset = NetBoxEndpoint.objects.all()


@register_model_view(NetBoxEndpoint, "list", path="", detail=False)
class NetBoxEndpointListView(generic.ObjectListView):
    queryset = NetBoxEndpoint.objects.all()
    table = NetBoxEndpointTable
    filterset = NetBoxEndpointFilterSet
    filterset_form = NetBoxEndpointFilterForm


@register_model_view(NetBoxEndpoint, "add", detail=False)
@register_model_view(NetBoxEndpoint, "edit")
class NetBoxEndpointEditView(generic.ObjectEditView):
    queryset = NetBoxEndpoint.objects.all()
    form = NetBoxEndpointForm


@register_model_view(NetBoxEndpoint, "delete")
class NetBoxEndpointDeleteView(generic.ObjectDeleteView):
    queryset = NetBoxEndpoint.objects.all()
