"""Provide NetBox CRUD views for Proxmox endpoint records."""

# Standard library imports
import csv
import io
import json

# Django imports
from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import redirect
import yaml

# NetBox Imports
from netbox.api.authentication import TokenAuthentication
from netbox.views import generic
from utilities.permissions import get_permission_for_model
from utilities.query import reapply_model_ordering
from utilities.views import register_model_view

# Proxbox Imports
from netbox_proxbox.models import ProxmoxEndpoint
from netbox_proxbox.tables import ProxmoxEndpointTable
from netbox_proxbox.filtersets import ProxmoxEndpointFilterSet
from netbox_proxbox.forms import (
    ProxmoxEndpointFilterForm,
    ProxmoxEndpointForm,
    ProxmoxEndpointImportForm,
)


__all__ = (
    "ProxmoxEndpointView",
    "ProxmoxEndpointListView",
    "ProxmoxEndpointEditView",
    "ProxmoxEndpointDeleteView",
    "ProxmoxEndpointBulkImportView",
    "ProxmoxEndpointExportView",
)


def _proxmox_export_fieldnames(include_sensitive: bool) -> tuple[str, ...]:
    base_fields = (
        "id",
        "name",
        "domain",
        "ip_address",
        "port",
        "mode",
        "version",
        "repoid",
        "username",
        "verify_ssl",
        "comments",
        "tags",
    )
    if include_sensitive:
        return (
            *base_fields,
            "password",
            "token_name",
            "token_value",
        )
    return (
        *base_fields,
        "token_name",
    )


def _serialize_proxmox_endpoint(
    endpoint: ProxmoxEndpoint, include_sensitive: bool
) -> dict[str, str]:
    tags_value = ",".join(sorted(tag.slug for tag in endpoint.tags.all()))
    row = {
        "id": str(endpoint.pk),
        "name": endpoint.name or "",
        "domain": endpoint.domain or "",
        "ip_address": str(endpoint.ip_address.address) if endpoint.ip_address else "",
        "port": str(endpoint.port),
        "mode": endpoint.mode or "",
        "version": endpoint.version or "",
        "repoid": endpoint.repoid or "",
        "username": endpoint.username or "",
        "verify_ssl": "true" if endpoint.verify_ssl else "false",
        "comments": endpoint.comments or "",
        "tags": tags_value,
        "token_name": endpoint.token_name or "",
    }
    if include_sensitive:
        row["password"] = endpoint.password or ""
        row["token_value"] = endpoint.token_value or ""
    return row


@register_model_view(ProxmoxEndpoint)
class ProxmoxEndpointView(generic.ObjectView):
    """
    Display a single Proxmox endpoint.
    """

    queryset = ProxmoxEndpoint.objects.all()


@register_model_view(ProxmoxEndpoint, "list", path="", detail=False)
class ProxmoxEndpointListView(generic.ObjectListView):
    """
    Display a list of Proxmox endpoints.
    """

    queryset = ProxmoxEndpoint.objects.all()
    table = ProxmoxEndpointTable
    filterset = ProxmoxEndpointFilterSet
    filterset_form = ProxmoxEndpointFilterForm
    template_name = "netbox_proxbox/proxmoxendpoint_list.html"


@register_model_view(ProxmoxEndpoint, "bulk_import", path="import", detail=False)
class ProxmoxEndpointBulkImportView(generic.BulkImportView):
    queryset = ProxmoxEndpoint.objects.all()
    model_form = ProxmoxEndpointImportForm


@register_model_view(ProxmoxEndpoint, "export", path="export", detail=False)
class ProxmoxEndpointExportView(generic.ObjectListView):
    queryset = ProxmoxEndpoint.objects.all()
    filterset = ProxmoxEndpointFilterSet

    allowed_formats = {"csv", "json", "yaml"}

    def get_required_permission(self):
        return get_permission_for_model(self.queryset.model, "view")

    def _validate_sensitive_export_token(self, request) -> bool:
        raw_token = (request.POST.get("netbox_token") or "").strip()
        if not raw_token:
            messages.error(
                request, "A valid NetBox token is required to export secrets."
            )
            return False

        header_value = raw_token
        if not (
            header_value.startswith("Token ") or header_value.startswith("Bearer ")
        ):
            if raw_token.startswith("nbt_"):
                header_value = f"Bearer {raw_token}"
            else:
                header_value = f"Token {raw_token}"

        request.META["HTTP_AUTHORIZATION"] = header_value
        authenticator = TokenAuthentication()
        try:
            auth_result = authenticator.authenticate(request)
        except Exception:
            auth_result = None

        if not auth_result:
            messages.error(request, "The provided NetBox token is invalid.")
            return False

        user, _token = auth_result
        if not user.is_authenticated:
            messages.error(
                request, "The provided NetBox token could not be authenticated."
            )
            return False

        if not user.has_perm("netbox_proxbox.view_proxmoxendpoint"):
            messages.error(
                request,
                "The provided token user does not have permission to view Proxmox endpoints.",
            )
            return False

        return True

    def _resolve_export_format(self, request) -> str:
        format_value = (
            request.GET.get("format") or request.POST.get("format") or "csv"
        ).lower()
        return format_value if format_value in self.allowed_formats else "csv"

    def _export_response(self, request, include_sensitive: bool, data_format: str):
        queryset = reapply_model_ordering(super().get_queryset(request))
        if self.filterset:
            queryset = self.filterset(request.GET, queryset, request=request).qs

        fieldnames = _proxmox_export_fieldnames(include_sensitive)
        rows = [
            _serialize_proxmox_endpoint(endpoint, include_sensitive)
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
            f'attachment; filename="netbox_proxbox_proxmox_endpoints_{suffix}.{data_format}"'
        )
        return response

    def get(self, request):
        data_format = self._resolve_export_format(request)
        return self._export_response(
            request,
            include_sensitive=False,
            data_format=data_format,
        )

    def post(self, request):
        include_sensitive = request.POST.get("include_sensitive") == "true"
        data_format = self._resolve_export_format(request)
        if include_sensitive and not self._validate_sensitive_export_token(request):
            return redirect("plugins:netbox_proxbox:proxmoxendpoint_list")
        return self._export_response(
            request,
            include_sensitive=include_sensitive,
            data_format=data_format,
        )


@register_model_view(ProxmoxEndpoint, "add", detail=False)
@register_model_view(ProxmoxEndpoint, "edit")
class ProxmoxEndpointEditView(generic.ObjectEditView):
    """
    Add or edit a Proxmox endpoint.
    """

    queryset = ProxmoxEndpoint.objects.all()
    form = ProxmoxEndpointForm


@register_model_view(ProxmoxEndpoint, "delete")
class ProxmoxEndpointDeleteView(generic.ObjectDeleteView):
    """
    Delete a Proxmox endpoint.
    """

    queryset = ProxmoxEndpoint.objects.all()
