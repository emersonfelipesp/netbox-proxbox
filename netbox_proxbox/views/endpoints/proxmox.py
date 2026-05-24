"""Provide NetBox CRUD views for Proxmox endpoint records."""

import json

from django.contrib import messages
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from netbox.api.authentication import TokenAuthentication
from netbox.views import generic
import requests
from utilities.permissions import get_permission_for_model
from utilities.query import reapply_model_ordering
from utilities.views import ViewTab, register_model_view

from netbox_proxbox.filtersets import ProxmoxEndpointFilterSet
from netbox_proxbox.forms import (
    ProxmoxEndpointFilterForm,
    ProxmoxEndpointForm,
    ProxmoxEndpointImportForm,
    ProxmoxEndpointSSHSettingsForm,
    ProxmoxEndpointSettingsForm,
)
from netbox_proxbox.models import ProxmoxEndpoint, ProxmoxNode
from netbox_proxbox.services.backend_context import (
    _build_request_candidates,
    get_fastapi_endpoint_with_token,
)
from netbox_proxbox.tables import ProxmoxEndpointTable
from netbox_proxbox.views.proxbox_access import permission_open_ssh_terminal
from netbox_proxbox.views.endpoints.proxmox_export import (
    _proxmox_export_fieldnames,
    _serialize_proxmox_endpoint,
)

__all__ = (
    "ProxmoxEndpointView",
    "ProxmoxEndpointListView",
    "ProxmoxEndpointEditView",
    "ProxmoxEndpointSettingsView",
    "ProxmoxEndpointSSHSettingsView",
    "ProxmoxEndpointSSHTerminalView",
    "ProxmoxEndpointSSHTerminalSessionView",
    "ProxmoxEndpointDeleteView",
    "ProxmoxEndpointBulkDeleteView",
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

    def get_extra_context(
        self, request: HttpRequest, instance: ProxmoxEndpoint
    ) -> dict[str, object]:
        """Expose resolved overwrite map plus per-field override origin to the template."""
        from netbox_proxbox.constants import OVERWRITE_FIELDS

        effective = instance.effective_overwrites()
        overwrite_rows = [
            {
                "field": name,
                "label": instance._meta.get_field(name).verbose_name,
                "value": effective[name],
                "is_override": getattr(instance, name) is not None,
            }
            for name in OVERWRITE_FIELDS
        ]
        return {"overwrite_rows": overwrite_rows}


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
    """Bulk import Proxmox endpoints from structured data.

    An ``id`` column exported from another NetBox instance is silently discarded —
    rows are always treated as new creates with auto-assigned PKs.
    """

    queryset = ProxmoxEndpoint.objects.all()
    model_form = ProxmoxEndpointImportForm

    def create_and_update_objects(
        self, form: ProxmoxEndpointImportForm, request: HttpRequest
    ) -> list[object]:
        # Strip any exported 'id' column before NetBox processes the records.
        # create_and_update_objects() prefetches by id first, then _process_import_records()
        # looks up each id — both must not see it, so we remove it here.
        for record in form.cleaned_data.get("data", []):
            record.pop("id", None)
        return super().create_and_update_objects(form, request)


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
                    token_obj = Token.objects.get(
                        pk=int(token_id), version=1, user=request.user
                    )
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


@register_model_view(ProxmoxEndpoint, "settings", path="settings")
class ProxmoxEndpointSettingsView(generic.ObjectEditView):
    """
    Edit Proxmox-specific per-endpoint overrides on a dedicated Settings tab.

    Hosts connection tunables (timeout / max_retries / retry_backoff) and the
    per-endpoint overwrite_* overrides. Empty overwrite values fall back to the
    global ProxboxPluginSettings.
    """

    queryset = ProxmoxEndpoint.objects.all()
    form = ProxmoxEndpointSettingsForm
    template_name = "netbox_proxbox/proxmoxendpoint_settings.html"
    tab = ViewTab(
        label="Settings",
        permission="netbox_proxbox.view_proxmoxendpoint",
        weight=900,
    )

    def get_extra_context(
        self, request: HttpRequest, instance: ProxmoxEndpoint
    ) -> dict[str, object]:
        """Expose grouped overwrite metadata so the template can render category cards."""
        from netbox_proxbox.constants import OVERWRITE_FIELD_GROUPS

        return {"overwrite_field_groups": OVERWRITE_FIELD_GROUPS}


@register_model_view(ProxmoxEndpoint, "ssh_settings", path="ssh-settings")
class ProxmoxEndpointSSHSettingsView(generic.ObjectEditView):
    """Edit endpoint-level SSH fallback credentials for browser terminals."""

    queryset = ProxmoxEndpoint.objects.all()
    form = ProxmoxEndpointSSHSettingsForm
    template_name = "netbox_proxbox/proxmoxendpoint_ssh_settings.html"
    tab = ViewTab(
        label="SSH",
        permission="netbox_proxbox.change_proxmoxendpoint",
        weight=925,
    )


def _terminal_websocket_url(base_websocket_url: str, websocket_path: str) -> str:
    """Append the SSH session path to the configured browser WebSocket base URL."""
    base = (base_websocket_url or "").rstrip("/")
    if base.endswith("/ws"):
        base = base[:-3]
    return f"{base}{websocket_path}"


@register_model_view(ProxmoxEndpoint, "ssh_terminal", path="ssh-terminal")
class ProxmoxEndpointSSHTerminalView(generic.ObjectView):
    """Browser terminal tab for Proxmox endpoint and node SSH sessions."""

    queryset = ProxmoxEndpoint.objects.all()
    template_name = "netbox_proxbox/proxmoxendpoint_ssh_terminal.html"
    tab = ViewTab(
        label="Terminal",
        permission=permission_open_ssh_terminal(),
        weight=950,
    )

    def get_extra_context(
        self, request: HttpRequest, instance: ProxmoxEndpoint
    ) -> dict[str, object]:
        nodes = ProxmoxNode.objects.filter(endpoint=instance).order_by("name")
        node_options = [
            {
                "id": node.pk,
                "name": node.name,
                "host": node.ip_address,
                "online": node.online,
            }
            for node in nodes
        ]
        return {
            "node_options": node_options,
            "endpoint_host": instance.ssh_host,
            "endpoint_ssh_ready": instance.has_ssh_terminal_credentials,
            "terminal_permission": permission_open_ssh_terminal(),
        }


@register_model_view(
    ProxmoxEndpoint,
    "ssh_terminal_session",
    path="ssh-terminal/session",
)
class ProxmoxEndpointSSHTerminalSessionView(View):
    """Create proxbox-api SSH terminal tickets without exposing backend API keys."""

    def post(self, request: HttpRequest, pk: int) -> JsonResponse:
        if not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required."}, status=401)
        if not request.user.has_perm(permission_open_ssh_terminal()):
            return JsonResponse({"error": "Permission denied."}, status=403)

        endpoint = get_object_or_404(
            ProxmoxEndpoint.objects.restrict(request.user, "view"),
            pk=pk,
        )
        try:
            body = json.loads(request.body.decode() or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON payload."}, status=400)

        try:
            cols = max(20, min(400, int(body.get("cols") or 120)))
            rows = max(5, min(200, int(body.get("rows") or 32)))
        except (TypeError, ValueError):
            return JsonResponse({"error": "Invalid terminal size."}, status=400)

        target_type = body.get("target_type")
        backend_payload = {
            "target_type": target_type,
            "endpoint_id": endpoint.pk,
            "actor": getattr(request.user, "username", "") or str(request.user),
            "cols": cols,
            "rows": rows,
        }
        if target_type == "node":
            node_id = body.get("node_id")
            node = ProxmoxNode.objects.filter(endpoint=endpoint, pk=node_id).first()
            if node is None:
                return JsonResponse({"error": "Node not found for endpoint."}, status=404)
            backend_payload["node_id"] = node.pk
            backend_payload["host"] = node.ip_address
        elif target_type == "endpoint":
            if not endpoint.has_ssh_terminal_credentials:
                return JsonResponse(
                    {"error": "Endpoint SSH fallback credentials are not configured."},
                    status=409,
                )
            backend_payload["host"] = endpoint.ssh_host
        else:
            return JsonResponse({"error": "Unsupported terminal target."}, status=400)

        fastapi_endpoint, context = get_fastapi_endpoint_with_token()
        if fastapi_endpoint is None or context is None or not context.http_url:
            return JsonResponse({"error": "No FastAPI endpoint configured."}, status=503)

        headers = dict(context.headers)
        headers["X-Proxbox-Actor"] = backend_payload["actor"]
        candidates = _build_request_candidates(
            context.http_url.rstrip("/"),
            context.ip_address_url.rstrip("/") if context.ip_address_url else None,
            "ssh/sessions",
            context.verify_ssl,
        )

        last_error = "Unable to reach proxbox-api."
        for url, verify_ssl in candidates:
            try:
                response = requests.post(
                    url,
                    json=backend_payload,
                    headers=headers,
                    verify=verify_ssl,
                    timeout=10,
                )
            except requests.RequestException as exc:
                last_error = str(exc)
                continue
            if response.status_code >= 400:
                return JsonResponse(
                    {"error": response.text or "proxbox-api rejected terminal session."},
                    status=response.status_code if response.status_code < 500 else 502,
                )
            try:
                data = response.json()
            except ValueError:
                return JsonResponse(
                    {"error": "proxbox-api returned a non-JSON terminal response."},
                    status=502,
                )
            websocket_base = (
                context.detail.get("websocket_url")
                or getattr(fastapi_endpoint, "websocket_url", "")
            )
            if not websocket_base:
                return JsonResponse(
                    {"error": "FastAPI endpoint WebSocket URL is not configured."},
                    status=503,
                )
            return JsonResponse(
                {
                    "session_id": data.get("session_id"),
                    "ticket": data.get("ticket"),
                    "websocket_url": _terminal_websocket_url(
                        str(websocket_base),
                        str(data.get("websocket_path") or ""),
                    ),
                    "expires_at": data.get("expires_at"),
                }
            )

        return JsonResponse({"error": last_error}, status=502)


@register_model_view(ProxmoxEndpoint, "delete")
class ProxmoxEndpointDeleteView(generic.ObjectDeleteView):
    """
    Delete a Proxmox endpoint.
    """

    queryset = ProxmoxEndpoint.objects.all()


@register_model_view(ProxmoxEndpoint, "bulk_delete", detail=False)
class ProxmoxEndpointBulkDeleteView(generic.BulkDeleteView):
    """Bulk-delete Proxmox endpoint records."""

    queryset = ProxmoxEndpoint.objects.all()
    filterset = ProxmoxEndpointFilterSet
    table = ProxmoxEndpointTable


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
