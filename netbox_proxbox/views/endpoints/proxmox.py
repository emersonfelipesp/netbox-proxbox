"""Provide NetBox CRUD views for Proxmox endpoint records."""

from __future__ import annotations

import json
from typing import ClassVar

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views import View
from netbox.api.authentication import TokenAuthentication
from netbox.views import generic
import requests
from utilities.permissions import get_permission_for_model
from utilities.query import reapply_model_ordering
from utilities.views import (
    ContentTypePermissionRequiredMixin,
    TokenConditionalLoginRequiredMixin,
    ViewTab,
    register_model_view,
)

from netbox.object_actions import (
    AddObject,
    BulkDelete,
    BulkExport,
    BulkImport,
    CloneObject,
    DeleteObject,
    EditObject,
    ObjectAction,
)
from netbox.views.generic.mixins import ActionsMixin

from netbox_proxbox.filtersets import ProxmoxEndpointFilterSet
from netbox_proxbox.forms import (
    ProxmoxEndpointFilterForm,
    ProxmoxEndpointForm,
    ProxmoxEndpointImportForm,
    ProxmoxEndpointSSHSettingsForm,
    ProxmoxEndpointSettingsForm,
)
from netbox_proxbox.models import (
    NodeSSHCredential,
    ProxboxPluginSettings,
    ProxmoxEndpoint,
    ProxmoxNode,
)
from netbox_proxbox.models.ssh_credential import (
    AUTH_METHOD_KEY,
    AUTH_METHOD_PASSWORD,
)
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
    "ProxmoxEndpointOverwriteBehaviorView",
    "ProxmoxEndpointListView",
    "ProxmoxEndpointEditView",
    "ProxmoxEndpointSettingsView",
    "ProxmoxEndpointSSHSettingsView",
    "ProxmoxEndpointSSHTerminalView",
    "ProxmoxEndpointSSHTerminalSessionView",
    "ProxmoxEndpointSyncJobsTabView",
    "ProxmoxEndpointBulkEnableAction",
    "ProxmoxEndpointBulkDisableAction",
    "ProxmoxEndpointBulkEnableView",
    "ProxmoxEndpointBulkDisableView",
    "ProxmoxEndpointDeleteView",
    "ProxmoxEndpointBulkDeleteView",
    "ProxmoxEndpointBulkImportView",
    "ProxmoxEndpointExportView",
    "ProxmoxExportQuickAddTokenView",
)


class ProxmoxEndpointBulkEnableAction(ObjectAction):
    """List-view action for enabling selected Proxmox endpoints."""

    name = "bulk_enable"
    label = _("Enable Selected")
    multi = True
    permissions_required = {"change"}
    template_name = "netbox_proxbox/buttons/proxmox_endpoint_bulk_enable.html"


class ProxmoxEndpointBulkDisableAction(ObjectAction):
    """List-view action for disabling selected Proxmox endpoints."""

    name = "bulk_disable"
    label = _("Disable Selected")
    multi = True
    permissions_required = {"change"}
    template_name = "netbox_proxbox/buttons/proxmox_endpoint_bulk_disable.html"


def _build_overwrite_row_groups(
    instance: ProxmoxEndpoint,
) -> list[tuple[str, list[dict[str, object]]]]:
    """Group the resolved overwrite map by category for the Overwrite Behavior tab.

    Returns ``[(group_label, [{field, label, value, is_override}, …]), …]`` in the
    same category order the Settings edit tab uses (``OVERWRITE_FIELD_GROUPS``).
    ``value`` is the effective flag (per-field override → global fallback) and
    ``is_override`` marks fields set explicitly on this endpoint.
    """
    from netbox_proxbox.constants import OVERWRITE_FIELD_GROUPS

    effective = instance.effective_overwrites()
    return [
        (
            group_label,
            [
                {
                    "field": name,
                    "label": instance._meta.get_field(name).verbose_name,
                    "value": effective[name],
                    "is_override": getattr(instance, name) is not None,
                }
                for name in group_fields
            ],
        )
        for group_label, group_fields in OVERWRITE_FIELD_GROUPS
    ]


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
    actions = (
        AddObject,
        BulkImport,
        BulkExport,
        ProxmoxEndpointBulkEnableAction,
        ProxmoxEndpointBulkDisableAction,
        BulkDelete,
    )


class _ProxmoxEndpointBulkEnabledView(
    TokenConditionalLoginRequiredMixin,
    ContentTypePermissionRequiredMixin,
    View,
):
    """Set the enabled state for selected Proxmox endpoints without side effects."""

    enabled: ClassVar[bool]
    verb: ClassVar[str]
    http_method_names: ClassVar[list[str]] = ["post"]

    def get_required_permission(self) -> str:
        """Require change permission on Proxmox endpoints."""
        return get_permission_for_model(ProxmoxEndpoint, "change")

    def _selected_queryset(self, request: HttpRequest) -> QuerySet[ProxmoxEndpoint]:
        """Resolve selected rows using NetBox list-view bulk selection semantics."""
        queryset = ProxmoxEndpoint.objects.restrict(request.user, "change")

        if request.POST.get("_all"):
            return ProxmoxEndpointFilterSet(
                request.GET,
                queryset,
                request=request,
            ).qs

        selected_ids = request.POST.getlist("pk") or request.POST.getlist("pk[]")
        if not selected_ids:
            return queryset.none()
        return queryset.filter(pk__in=selected_ids)

    def _return_url(self, request: HttpRequest) -> str:
        """Redirect back to the originating list page after the bulk action."""
        return (
            request.POST.get("return_url")
            or request.META.get("HTTP_REFERER")
            or reverse("plugins:netbox_proxbox:proxmoxendpoint_list")
        )

    def post(self, request: HttpRequest) -> HttpResponseRedirect:
        """Bulk-update only the local enabled flag for selected endpoints."""
        selected_ids = request.POST.getlist("pk") or request.POST.getlist("pk[]")
        if not selected_ids and not request.POST.get("_all"):
            messages.error(
                request,
                _("Select at least one Proxmox endpoint to {verb}.").format(
                    verb=self.verb
                ),
            )
            return HttpResponseRedirect(self._return_url(request))

        queryset = self._selected_queryset(request)
        matched_count = queryset.count()
        updated_count = queryset.exclude(enabled=self.enabled).update(
            enabled=self.enabled
        )

        if updated_count:
            messages.success(
                request,
                _("{count} Proxmox endpoint(s) {verb}.").format(
                    count=updated_count,
                    verb=_("enabled") if self.enabled else _("disabled"),
                ),
            )
        elif matched_count:
            messages.info(
                request,
                _("Selected Proxmox endpoint(s) were already {state}.").format(
                    state=_("enabled") if self.enabled else _("disabled")
                ),
            )
        else:
            messages.warning(
                request,
                _("No selected Proxmox endpoints were available to {verb}.").format(
                    verb=self.verb
                ),
            )

        return HttpResponseRedirect(self._return_url(request))


@register_model_view(
    ProxmoxEndpoint,
    "bulk_enable",
    path="enable-selected",
    detail=False,
)
class ProxmoxEndpointBulkEnableView(_ProxmoxEndpointBulkEnabledView):
    """Enable selected Proxmox endpoint records."""

    enabled = True
    verb = "enable"


@register_model_view(
    ProxmoxEndpoint,
    "bulk_disable",
    path="disable-selected",
    detail=False,
)
class ProxmoxEndpointBulkDisableView(_ProxmoxEndpointBulkEnabledView):
    """Disable selected Proxmox endpoint records."""

    enabled = False
    verb = "disable"


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
class ProxmoxEndpointSettingsView(ActionsMixin, generic.ObjectEditView):
    """
    Edit Proxmox-specific per-endpoint overrides on a dedicated Settings tab.

    Hosts connection tunables (timeout / max_retries / retry_backoff) and the
    per-endpoint overwrite_* overrides. Empty overwrite values fall back to the
    global ProxboxPluginSettings.
    """

    queryset = ProxmoxEndpoint.objects.all()
    form = ProxmoxEndpointSettingsForm
    template_name = "netbox_proxbox/proxmoxendpoint_settings.html"
    # Same single-object actions the detail view exposes, so the shared object
    # header renders the identical Clone/Edit/Delete buttons on this edit tab.
    actions = (CloneObject, EditObject, DeleteObject)
    tab = ViewTab(
        label="Settings",
        permission="netbox_proxbox.view_proxmoxendpoint",
        weight=900,
    )

    def get_extra_context(
        self, request: HttpRequest, instance: ProxmoxEndpoint
    ) -> dict[str, object]:
        """Expose grouped overwrite metadata so the template can render category cards."""
        from netbox_proxbox.constants import (
            OVERWRITE_FIELD_GROUPS,
            SYNC_MODE_FIELD_GROUPS,
        )

        return {
            "overwrite_field_groups": OVERWRITE_FIELD_GROUPS,
            "sync_mode_field_groups": SYNC_MODE_FIELD_GROUPS,
            # ObjectEditView (unlike ObjectView) does not inject ``tab`` into the
            # context, so expose it here for the object tab strip in the template
            # to highlight this Settings tab as active (and to keep the primary
            # detail tab, gated on ``{% if not tab %}``, inactive).
            "tab": self.tab,
            # ObjectEditView does not compute ``actions`` either; supply the
            # permitted single-object actions so the shared object header renders
            # the same Clone/Edit/Delete buttons as the detail page.
            "actions": self.get_permitted_actions(request.user, model=instance),
        }


@register_model_view(ProxmoxEndpoint, "overwrite_behavior", path="overwrite-behavior")
class ProxmoxEndpointOverwriteBehaviorView(generic.ObjectView):
    """Read-only tab showing the resolved sync-overwrite behavior by category.

    Moves the former detail-page "Sync Overwrite Behavior" card onto its own tab
    and splits the ``overwrite_*`` flags into per-category sub-tabs (Device /
    Virtual Machine / Cluster / Node Interface / Storage / VM Interface / IP
    Address), mirroring the grouping of the Settings edit tab.
    """

    queryset = ProxmoxEndpoint.objects.all()
    template_name = "netbox_proxbox/proxmoxendpoint_overwrite_behavior.html"
    tab = ViewTab(
        label="Overwrite Behavior",
        permission="netbox_proxbox.view_proxmoxendpoint",
        weight=905,
    )

    def get_extra_context(
        self, request: HttpRequest, instance: ProxmoxEndpoint
    ) -> dict[str, object]:
        """Expose the resolved overwrite map grouped by category for the sub-tabs."""
        return {"overwrite_row_groups": _build_overwrite_row_groups(instance)}


@register_model_view(ProxmoxEndpoint, "ssh_settings", path="ssh-settings")
class ProxmoxEndpointSSHSettingsView(ActionsMixin, generic.ObjectEditView):
    """Edit endpoint-level SSH fallback credentials for browser terminals."""

    queryset = ProxmoxEndpoint.objects.all()
    form = ProxmoxEndpointSSHSettingsForm
    template_name = "netbox_proxbox/proxmoxendpoint_ssh_settings.html"
    actions = (CloneObject, EditObject, DeleteObject)
    tab = ViewTab(
        label="SSH",
        permission="netbox_proxbox.change_proxmoxendpoint",
        weight=925,
    )

    def get_extra_context(
        self, request: HttpRequest, instance: ProxmoxEndpoint
    ) -> dict[str, object]:
        """Expose ``tab`` + ``actions`` so the shared object header renders.

        ``ObjectEditView`` injects neither ``tab`` (needed to highlight the
        active SSH tab) nor ``actions`` (needed for the header's Clone/Edit/Delete
        buttons), so the object header in ``proxmoxendpoint_ssh_settings.html``
        matches the detail page.
        """
        return {
            "tab": self.tab,
            "actions": self.get_permitted_actions(request.user, model=instance),
        }


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
        cred_node_ids = set(
            NodeSSHCredential.objects.filter(node__endpoint=instance).values_list(
                "node_id", flat=True
            )
        )
        node_options = [
            {
                "id": node.pk,
                "name": node.name,
                "host": node.ip_address,
                "online": node.online,
                # True when a NodeSSHCredential is already stored for this node.
                # The Terminal-tab JS uses this to decide whether to prompt for
                # credentials before connecting.
                "ssh_ready": node.pk in cred_node_ids,
            }
            for node in nodes
        ]
        can_store_credentials = request.user.has_perm(
            "netbox_proxbox.add_nodesshcredential"
        ) and request.user.has_perm("netbox_proxbox.change_nodesshcredential")
        return {
            "node_options": node_options,
            "endpoint_host": instance.ssh_host,
            "endpoint_ssh_ready": instance.has_ssh_terminal_credentials,
            "endpoint_ssh_access_enabled": instance.ssh_access_enabled,
            "can_store_credentials": can_store_credentials,
            "terminal_permission": permission_open_ssh_terminal(),
        }


def _validate_terminal_credential(credential: object) -> tuple[dict | None, str | None]:
    """Validate a credential object typed into the Terminal-tab modal.

    Returns ``(normalized_dict, None)`` on success or ``(None, error)`` on
    failure. The normalized dict carries ``username``, ``port``, ``auth_method``,
    ``password``, ``private_key``, and ``known_host_fingerprint``. A pinned
    host-key fingerprint is mandatory for both the store and one-shot paths
    because proxbox-api refuses to connect without it.
    """
    if not isinstance(credential, dict):
        return None, "Credential payload must be an object."
    username = str(credential.get("username") or "").strip()
    if not username:
        return None, "SSH username is required."
    fingerprint = str(credential.get("known_host_fingerprint") or "").strip()
    if not fingerprint:
        return None, (
            'Host-key fingerprint is required. Use "Fetch host key" to obtain it.'
        )
    password = str(credential.get("password") or "")
    private_key = str(credential.get("private_key") or "")
    auth_method = str(credential.get("auth_method") or "").strip().lower()
    if auth_method not in (AUTH_METHOD_PASSWORD, AUTH_METHOD_KEY):
        auth_method = AUTH_METHOD_KEY if private_key.strip() else AUTH_METHOD_PASSWORD
    if auth_method == AUTH_METHOD_PASSWORD and not password:
        return None, "Password is required for password authentication."
    if auth_method == AUTH_METHOD_KEY and not private_key.strip():
        return None, "Private key is required for key authentication."
    try:
        port = int(credential.get("port") or 22)
    except (TypeError, ValueError):
        return None, "SSH port must be a number."
    if port < 1 or port > 65535:
        return None, "SSH port must be between 1 and 65535."
    return {
        "username": username,
        "port": port,
        "auth_method": auth_method,
        "password": password,
        "private_key": private_key,
        "known_host_fingerprint": fingerprint,
    }, None


def _one_shot_payload(data: dict) -> dict:
    """Build the proxbox-api ``one_shot_credential`` body from validated data."""
    payload = {
        "username": data["username"],
        "port": data["port"],
        "known_host_fingerprint": data["known_host_fingerprint"],
    }
    if data["auth_method"] == AUTH_METHOD_KEY:
        payload["private_key"] = data["private_key"]
    else:
        payload["password"] = data["password"]
    return payload


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
            ProxmoxEndpoint.objects.restrict(request.user, "view").restrict(
                request.user, "open_ssh_terminal"
            ),
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
        credential = body.get("credential")
        store = bool(body.get("store"))
        backend_payload = {
            "target_type": target_type,
            "endpoint_id": endpoint.pk,
            "actor": getattr(request.user, "username", "") or str(request.user),
            "cols": cols,
            "rows": rows,
        }

        # A credential typed into the modal (store OR one-shot) opens SSH from the
        # inline material, bypassing the plugin's stored-credential access gate, so
        # enforce the endpoint's SSH access method here explicitly.
        if credential is not None and not endpoint.ssh_access_enabled:
            return JsonResponse(
                {
                    "error": (
                        "SSH access is disabled on this endpoint. Set the access "
                        "method to 'API + SSH' to use the terminal."
                    )
                },
                status=403,
            )

        if target_type == "node":
            node_id = body.get("node_id")
            node = ProxmoxNode.objects.filter(endpoint=endpoint, pk=node_id).first()
            if node is None:
                return JsonResponse(
                    {"error": "Node not found for endpoint."}, status=404
                )
            backend_payload["node_id"] = node.pk
            backend_payload["host"] = node.ip_address
            if credential is not None:
                error = self._apply_node_credential(
                    request, node, credential, store, backend_payload
                )
                if error is not None:
                    return error
        elif target_type == "endpoint":
            if credential is not None:
                if store:
                    return JsonResponse(
                        {
                            "error": (
                                "Store endpoint SSH credentials from the endpoint's "
                                "SSH settings tab, not the terminal modal."
                            )
                        },
                        status=400,
                    )
                host = (endpoint.ssh_host or "").strip()
                if not host:
                    return JsonResponse(
                        {"error": "Endpoint has no resolvable SSH host."},
                        status=422,
                    )
                data, error = _validate_terminal_credential(credential)
                if error is not None:
                    return JsonResponse({"error": error}, status=400)
                backend_payload["host"] = host
                backend_payload["one_shot_credential"] = _one_shot_payload(data)
            else:
                if not endpoint.has_ssh_terminal_credentials:
                    return JsonResponse(
                        {
                            "error": (
                                "Endpoint SSH fallback credentials are not configured."
                            )
                        },
                        status=409,
                    )
                backend_payload["host"] = endpoint.ssh_host
        else:
            return JsonResponse({"error": "Unsupported terminal target."}, status=400)

        fastapi_endpoint, context = get_fastapi_endpoint_with_token()
        if fastapi_endpoint is None or context is None or not context.http_url:
            return JsonResponse(
                {"error": "No FastAPI endpoint configured."}, status=503
            )

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
                    {
                        "error": response.text
                        or "proxbox-api rejected terminal session."
                    },
                    status=response.status_code if response.status_code < 500 else 502,
                )
            try:
                data = response.json()
            except ValueError:
                return JsonResponse(
                    {"error": "proxbox-api returned a non-JSON terminal response."},
                    status=502,
                )
            websocket_base = context.detail.get("websocket_url") or getattr(
                fastapi_endpoint, "websocket_url", ""
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

    def _apply_node_credential(
        self,
        request: HttpRequest,
        node: ProxmoxNode,
        credential: object,
        store: bool,
        backend_payload: dict,
    ) -> JsonResponse | None:
        """Handle a modal-supplied node credential (store or one-shot).

        On the **store** path it persists an encrypted ``NodeSSHCredential`` and
        leaves ``backend_payload`` untouched so proxbox-api fetches the freshly
        stored secret. On the **one-shot** path it adds ``one_shot_credential`` to
        ``backend_payload`` and stores nothing. Returns a ``JsonResponse`` on
        failure, or ``None`` on success.
        """
        data, error = _validate_terminal_credential(credential)
        if error is not None:
            return JsonResponse({"error": error}, status=400)

        if not store:
            backend_payload["one_shot_credential"] = _one_shot_payload(data)
            return None

        # Store path: persist an encrypted NodeSSHCredential, then open a normal
        # session that fetches the stored secret.
        if not (
            request.user.has_perm("netbox_proxbox.add_nodesshcredential")
            and request.user.has_perm("netbox_proxbox.change_nodesshcredential")
        ):
            return JsonResponse(
                {
                    "error": (
                        "You do not have permission to store SSH credentials. "
                        'Use "Use once" instead.'
                    )
                },
                status=403,
            )

        key = ProxboxPluginSettings.get_solo().encryption_key or ""
        if not key:
            return JsonResponse(
                {
                    "error": (
                        "Cannot store credentials: the plugin encryption key is "
                        'not configured. Use "Use once" instead.'
                    )
                },
                status=503,
            )

        cred = NodeSSHCredential.objects.filter(node=node).first()
        if cred is None:
            cred = NodeSSHCredential(node=node)
        cred.username = data["username"]
        cred.port = data["port"]
        cred.auth_method = data["auth_method"]
        cred.known_host_fingerprint = data["known_host_fingerprint"]
        if data["auth_method"] == AUTH_METHOD_KEY:
            cred.set_private_key(data["private_key"], key=key)
            cred.password_enc = ""
        else:
            cred.set_password(data["password"], key=key)
            cred.private_key_enc = ""
        try:
            cred.full_clean()
            cred.save()
        except ValidationError as exc:
            return JsonResponse(
                {"error": "; ".join(exc.messages) or "Invalid SSH credential."},
                status=400,
            )
        return None


@register_model_view(ProxmoxEndpoint, "sync_jobs", path="sync-jobs")
class ProxmoxEndpointSyncJobsTabView(generic.ObjectView):
    """Read-only tab listing Proxbox sync jobs scoped to this Proxmox endpoint."""

    queryset = ProxmoxEndpoint.objects.all()
    template_name = "netbox_proxbox/proxmoxendpoint_sync_jobs.html"
    tab = ViewTab(
        label="Sync Jobs",
        permission="netbox_proxbox.view_proxmoxendpoint",
        weight=875,
    )

    def get_extra_context(
        self, request: HttpRequest, instance: ProxmoxEndpoint
    ) -> dict[str, object]:
        from core.models import Job
        from netbox_proxbox.jobs import is_proxbox_sync_job

        endpoint_pk_str = str(instance.pk)
        jobs_qs = Job.objects.restrict(request.user, "view").order_by("-created")

        endpoint_jobs: list[Job] = []
        for job in jobs_qs.iterator():
            if not is_proxbox_sync_job(job):
                continue
            data = getattr(job, "data", None) or {}
            params = data.get("proxbox_sync", {}).get("params", {})
            endpoint_ids = params.get("proxmox_endpoint_ids", [])
            # Include jobs targeting this endpoint or jobs with no endpoint filter
            # (which apply to all endpoints).
            if not endpoint_ids or endpoint_pk_str in [str(e) for e in endpoint_ids]:
                endpoint_jobs.append(job)

        return {"endpoint_sync_jobs": endpoint_jobs}


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
