"""Provide NetBox CRUD and OpenAPI tab views for FastAPI endpoint records."""

from django.http import HttpRequest
from netbox.views import generic
from utilities.views import ViewTab, register_model_view

from netbox_proxbox.filtersets import FastAPIEndpointFilterSet
from netbox_proxbox.forms import (
    FastAPIEndpointFilterForm,
    FastAPIEndpointForm,
    FastAPIEndpointImportForm,
)
from netbox_proxbox.models import FastAPIEndpoint
from netbox_proxbox.services.openapi_schema import get_cached_openapi_schema
from netbox_proxbox.tables import FastAPIEndpointTable


__all__ = (
    "FastAPIEndpointView",
    "FastAPIOpenAPIView",
    "FastAPIEndpointListView",
    "FastAPIEndpointBulkImportView",
    "FastAPIEndpointEditView",
    "FastAPIEndpointDeleteView",
)


@register_model_view(FastAPIEndpoint)
class FastAPIEndpointView(generic.ObjectView):
    """Detail view for a proxbox-api (FastAPI) backend endpoint."""

    queryset = FastAPIEndpoint.objects.all()


@register_model_view(FastAPIEndpoint, "openapi", path="openapi")
class FastAPIOpenAPIView(generic.ObjectView):
    """Detail tab that renders backend OpenAPI schema metadata and endpoints."""

    queryset = FastAPIEndpoint.objects.all()
    template_name = "netbox_proxbox/fastapiendpoint_openapi.html"
    tab = ViewTab(
        label="OpenAPI",
        permission="netbox_proxbox.view_fastapiendpoint",
        weight=1050,
    )

    def get_extra_context(
        self, request: HttpRequest, instance: FastAPIEndpoint
    ) -> dict[str, object]:
        """Return extra context."""
        force_refresh = str(request.GET.get("refresh", "")).strip().lower() in {
            "1",
            "true",
            "yes",
        }
        openapi_data = get_cached_openapi_schema(instance, force_refresh=force_refresh)
        return {
            "openapi_data": openapi_data,
            "openapi_force_refresh": force_refresh,
        }


@register_model_view(FastAPIEndpoint, "list", path="", detail=False)
class FastAPIEndpointListView(generic.ObjectListView):
    """Filterable list of FastAPI backend endpoint records."""

    queryset = FastAPIEndpoint.objects.all()
    table = FastAPIEndpointTable
    filterset = FastAPIEndpointFilterSet
    filterset_form = FastAPIEndpointFilterForm
    template_name = "netbox_proxbox/fastapiendpoint_list.html"


@register_model_view(FastAPIEndpoint, "bulk_import", path="import", detail=False)
class FastAPIEndpointBulkImportView(generic.BulkImportView):
    """Bulk import FastAPI endpoints from structured data."""

    queryset = FastAPIEndpoint.objects.all()
    model_form = FastAPIEndpointImportForm


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
