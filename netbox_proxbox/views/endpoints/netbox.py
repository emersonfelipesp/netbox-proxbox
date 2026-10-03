"""Provide NetBox CRUD views for remote NetBox endpoint records."""

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.debug import sensitive_variables
from netbox.views import generic
from utilities.permissions import get_permission_for_model
from utilities.views import register_model_view

from netbox_proxbox.sensitive_data import require_sensitive_data_access
from netbox_proxbox.views.endpoints.sensitive_export import (
    CredentialSafeListMixin,
    SensitiveExportMixin,
)

from netbox_proxbox.filtersets import NetBoxEndpointFilterSet
from netbox_proxbox.forms import (
    NetBoxEndpointFilterForm,
    NetBoxEndpointForm,
    NetBoxEndpointImportForm,
)
from netbox_proxbox.models import NetBoxEndpoint
from netbox_proxbox.tables import NetBoxEndpointTable
from netbox_proxbox.views.endpoints.netbox_export import (
    _netbox_export_fieldnames,
    _serialize_netbox_endpoint,
)


__all__ = (
    "NetBoxEndpointView",
    "NetBoxEndpointListView",
    "NetBoxEndpointBulkImportView",
    "NetBoxEndpointEditView",
    "NetBoxEndpointDeleteView",
    "NetBoxEndpointExportView",
)


@register_model_view(NetBoxEndpoint)
class NetBoxEndpointView(generic.ObjectView):
    """Detail view for a remote NetBox API endpoint configuration."""

    queryset = NetBoxEndpoint.objects.all()


@register_model_view(NetBoxEndpoint, "list", path="", detail=False)
class NetBoxEndpointListView(CredentialSafeListMixin, generic.ObjectListView):
    """Filterable list of NetBox endpoint records."""

    queryset = NetBoxEndpoint.objects.all()
    table = NetBoxEndpointTable
    filterset = NetBoxEndpointFilterSet
    filterset_form = NetBoxEndpointFilterForm
    template_name = "netbox_proxbox/netboxendpoint_list.html"
    actions = ()


@register_model_view(NetBoxEndpoint, "bulk_import", path="import", detail=False)
class NetBoxEndpointBulkImportView(generic.BulkImportView):
    """Bulk import NetBox endpoints from structured data.

    NetBoxEndpoint is a singleton — at most one record is allowed. If an existing
    record is found during import, the user is prompted to confirm the override before
    the existing record is deleted and replaced with the imported data.

    An ``id`` column exported from another NetBox instance is silently discarded.
    """

    queryset = NetBoxEndpoint.objects.all()
    model_form = NetBoxEndpointImportForm

    def post(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        """Intercept if singleton exists and override is not yet confirmed."""
        existing = NetBoxEndpoint.objects.first()
        if existing and request.POST.get("confirm_override") != "true":
            # Let the parent parse and validate the form so we can check for errors
            # before showing the confirmation page.
            form = self.get_form()
            if form.is_valid():
                return render(
                    request,
                    "netbox_proxbox/singleton_import_confirm.html",
                    {
                        "existing": existing,
                        "model_name": NetBoxEndpoint._meta.verbose_name,
                        "import_url": request.path,
                        "return_url": reverse(
                            "plugins:netbox_proxbox:netboxendpoint_list"
                        ),
                        "post_items": list(request.POST.lists()),
                    },
                )
        return super().post(request, *args, **kwargs)

    def create_and_update_objects(
        self, form: NetBoxEndpointImportForm, request: HttpRequest
    ) -> list[object]:
        """Strip exported ``id`` column and handle singleton replacement."""
        for record in form.cleaned_data.get("data", []):
            record.pop("id", None)

        if request.POST.get("confirm_override") == "true":
            existing = NetBoxEndpoint.objects.first()
            if existing:
                existing.delete()

        return super().create_and_update_objects(form, request)


@register_model_view(NetBoxEndpoint, "export", path="export", detail=False)
class NetBoxEndpointExportView(SensitiveExportMixin, generic.ObjectListView):
    """Download filtered NetBox endpoints as CSV, JSON, or YAML; secrets require explicit authorization."""

    queryset = NetBoxEndpoint.objects.all()
    filterset = NetBoxEndpointFilterSet
    allowed_formats = {"csv", "json", "yaml"}

    def get_required_permission(self) -> str:
        """Require model ``view`` on NetBox endpoints (same as the list)."""
        return get_permission_for_model(self.queryset.model, "view")

    def _validate_sensitive_export_token(self, request: HttpRequest) -> bool:
        """Authorize the current actor; supplied tokens do not confer access."""
        require_sensitive_data_access(request.user)
        return True

    def _resolve_export_format(self, request: HttpRequest) -> str:
        """Normalize ``format`` from GET/POST to one of ``allowed_formats`` (default csv)."""
        format_value = (
            request.POST.get("format") or request.GET.get("format") or "csv"
        ).lower()
        return format_value if format_value in self.allowed_formats else "csv"

    @sensitive_variables()
    def _export_response(
        self, request: HttpRequest, include_sensitive: bool, data_format: str
    ) -> HttpResponse:
        """Serialize the current filtered queryset to a downloadable HTTP response."""
        import csv
        import io
        import json

        import yaml

        queryset = self.authorized_export_queryset(
            request, include_sensitive=include_sensitive
        )

        fieldnames = _netbox_export_fieldnames(include_sensitive)
        rows = [
            _serialize_netbox_endpoint(endpoint, include_sensitive, user=request.user)
            for endpoint in queryset
        ]

        if data_format == "json":
            payload = json.dumps(rows, indent=2)
            response = HttpResponse(payload, content_type="application/json")
        elif data_format == "yaml":
            payload = yaml.safe_dump(rows, sort_keys=False)
            response = HttpResponse(payload, content_type="application/yaml")
        else:
            buffer = io.StringIO()
            writer = csv.DictWriter(buffer, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
            response = HttpResponse(buffer.getvalue(), content_type="text/csv")

        suffix = "with-secrets" if include_sensitive else "safe"
        response["Content-Disposition"] = (
            f'attachment; filename="netbox_proxbox_netbox_endpoints_{suffix}.{data_format}"'
        )
        if include_sensitive:
            response["Cache-Control"] = "no-store"
        return response

    def get(self, request: HttpRequest) -> HttpResponse:
        """Export without token credentials (safe columns only)."""
        data_format = self._resolve_export_format(request)
        return self._export_response(
            request,
            include_sensitive=False,
            data_format=data_format,
        )

    def post(self, request: HttpRequest) -> HttpResponse:
        """Export with optional secrets under the current actor's explicit grant."""
        include_sensitive = request.POST.get("include_sensitive") == "true"
        data_format = self._resolve_export_format(request)
        return self.protected_export_response(
            request,
            include_sensitive=include_sensitive,
            data_format=data_format,
        )


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
