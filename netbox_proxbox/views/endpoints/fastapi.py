"""Provide NetBox CRUD views for FastAPI backend endpoint records."""

from netbox.views import generic
from utilities.views import register_model_view

from netbox_proxbox.filtersets import FastAPIEndpointFilterSet
from netbox_proxbox.forms import FastAPIEndpointFilterForm, FastAPIEndpointForm
from netbox_proxbox.models import FastAPIEndpoint
from netbox_proxbox.tables import FastAPIEndpointTable


__all__ = (
    "FastAPIEndpointView",
    "FastAPIEndpointListView",
    "FastAPIEndpointEditView",
    "FastAPIEndpointDeleteView",
)


@register_model_view(FastAPIEndpoint)
class FastAPIEndpointView(generic.ObjectView):
    """Detail view for a proxbox-api (FastAPI) backend endpoint."""

    queryset = FastAPIEndpoint.objects.all()


@register_model_view(FastAPIEndpoint, "list", path="", detail=False)
class FastAPIEndpointListView(generic.ObjectListView):
    """Filterable list of FastAPI backend endpoint records."""

    queryset = FastAPIEndpoint.objects.all()
    table = FastAPIEndpointTable
    filterset = FastAPIEndpointFilterSet
    filterset_form = FastAPIEndpointFilterForm
    template_name = "netbox_proxbox/fastapiendpoint_list.html"


@register_model_view(FastAPIEndpoint, "add", detail=False)
@register_model_view(FastAPIEndpoint, "edit")
class FastAPIEndpointEditView(generic.ObjectEditView):
    """Create or edit a FastAPI endpoint (URL, auth, and SSL options)."""

    queryset = FastAPIEndpoint.objects.all()
    form = FastAPIEndpointForm


@register_model_view(FastAPIEndpoint, "delete")
class FastAPIEndpointDeleteView(generic.ObjectDeleteView):
    """Delete a FastAPI endpoint record."""

    queryset = FastAPIEndpoint.objects.all()
