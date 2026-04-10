"""Provide NetBox CRUD views for Proxmox endpoint records."""

from django.contrib import messages
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.views import View
from netbox.api.authentication import TokenAuthentication
from netbox.views import generic
from utilities.permissions import get_permission_for_model
from utilities.query import reapply_model_ordering
from utilities.views import register_model_view

from netbox_proxbox.filtersets import ProxmoxEndpointFilterSet
from netbox_proxbox.forms import (
    ProxmoxEndpointFilterForm,
    ProxmoxEndpointForm,
    ProxmoxEndpointImportForm,
)
from netbox_proxbox.models import ProxmoxEndpoint
from netbox_proxbox.tables import ProxmoxEndpointTable
from netbox_proxbox.views.endpoints.proxmox_export import (
    _proxmox_export_fieldnames,
    _serialize_proxmox_endpoint,
)

__all__ = (
    "ProxmoxEndpointView",
    "ProxmoxEndpointListView",
    "ProxmoxEndpointEditView",
    "ProxmoxEndpointDeleteView",
    "ProxmoxEndpointBulkImportView",
    "ProxmoxEndpointExportView",
    "ProxmoxExportQuickAddTokenView",
)


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
    """Bulk import Proxmox endpoints from structured data."""

    queryset = ProxmoxEndpoint.objects.all()
    model_form = ProxmoxEndpointImportForm


@register_model_view(ProxmoxEndpoint, "export", path="export", detail=False)
class ProxmoxEndpointExportView(generic.ObjectListView):
    """Download filtered Proxmox endpoints as CSV, JSON, or YAML; secrets require token proof."""

    queryset = ProxmoxEndpoint.objects.all()
    filterset = ProxmoxEndpointFilterSet
    allowed_formats = {"csv", "json", "yaml"}

    def get_required_permission(self) -> str:
        """Require model ``view`` on Proxmox endpoints (same as the list)."""
        return get_permission_for_model(self.queryset.model, "view")

    def _validate_sensitive_export_token(self, request: HttpRequest) -> bool:
        """Confirm POSTed NetBox API token maps to a user allowed to view Proxmox endpoints.

        Supports three modes based on the ``token_version`` POST field:
        - ``v1``: ``v1_manual_token`` (raw plaintext) takes priority over a dropdown
          ``token_id`` selection.  Either must be provided.
        - ``v2``: construct a Bearer header from ``token_key`` and ``token_secret`` fields.
        - Fallback (no ``token_version``): legacy ``netbox_token`` single-field format.
        """
        from users.models import Token

        token_version = (request.POST.get("token_version") or "").strip()

        if token_version == "v1":
            # A manually entered token overrides the dropdown selection.
            manual_token = (request.POST.get("v1_manual_token") or "").strip()
            if manual_token:
                # Accept raw plaintext, or a prefixed "Token <value>" string.
                if manual_token.startswith("Token "):
                    header_value = manual_token
                else:
                    header_value = f"Token {manual_token}"
            else:
                token_id = (request.POST.get("token_id") or "").strip()
                if not token_id:
                    messages.error(
                        request,
                        "Select a v1 token or enter one manually to export secrets.",
                    )
                    return False
                try:
                    token_obj = Token.objects.get(pk=int(token_id), version=1)
                except (Token.DoesNotExist, ValueError):
                    messages.error(request, "The selected v1 token could not be found.")
                    return False
                plaintext = (token_obj.plaintext or "").strip()
                if not plaintext:
                    messages.error(
                        request,
                        "The selected v1 token does not have a usable plaintext value.",
                    )
                    return False
                header_value = f"Token {plaintext}"

        elif token_version == "v2":
            token_key = (request.POST.get("token_key") or "").strip()
            token_secret = (request.POST.get("token_secret") or "").strip()
            if not token_key or not token_secret:
                messages.error(
                    request,
                    "Both token key and token secret are required for v2 authentication.",
                )
                return False
            header_value = f"Bearer {token_key}.{token_secret}"

        else:
            # Legacy fallback: raw token string in netbox_token field.
            raw_token = (request.POST.get("netbox_token") or "").strip()
            if not raw_token:
                messages.error(
                    request, "A valid NetBox token is required to export secrets."
                )
                return False
            if raw_token.startswith("Token ") or raw_token.startswith("Bearer "):
                header_value = raw_token
            elif raw_token.startswith("nbt_"):
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

    def _resolve_export_format(self, request: HttpRequest) -> str:
        """Normalize ``format`` from GET/POST to one of ``allowed_formats`` (default csv)."""
        format_value = (
            request.GET.get("format") or request.POST.get("format") or "csv"
        ).lower()
        return format_value if format_value in self.allowed_formats else "csv"

    def _export_response(
        self, request: HttpRequest, include_sensitive: bool, data_format: str
    ) -> HttpResponse:
        """Serialize the current filtered queryset to a downloadable HTTP response."""
        import csv
        import io
        import json

        import yaml

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

    def get(self, request: HttpRequest) -> HttpResponse:
        """Export without passwords or token values (safe columns only)."""
        data_format = self._resolve_export_format(request)
        return self._export_response(
            request,
            include_sensitive=False,
            data_format=data_format,
        )

    def post(self, request: HttpRequest) -> HttpResponse:
        """Export with optional secrets after ``_validate_sensitive_export_token`` succeeds."""
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


@register_model_view(
    ProxmoxEndpoint,
    "quick_add_token",
    path="export/quick-add-token",
    detail=False,
)
class ProxmoxExportQuickAddTokenView(View):
    """Create a temporary v1 NetBox API token for use with the sensitive export modal.

    The token is created under the current user's account and its plaintext is returned
    once in the JSON response.  The UI warns the user to delete or securely store the
    token after the export is complete.
    """

    def post(self, request: HttpRequest) -> JsonResponse:
        from users.models import Token

        if not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required."}, status=401)

        if not request.user.has_perm("users.add_token"):
            return JsonResponse(
                {"error": "You do not have permission to create tokens."}, status=403
            )

        try:
            token = Token(version=1, user=request.user)
            token.full_clean()
            token.save()
        except Exception as exc:
            return JsonResponse({"error": f"Failed to create token: {exc}"}, status=500)

        return JsonResponse(
            {
                "id": token.pk,
                "display": str(token),
                "plaintext": token.plaintext,
            }
        )
