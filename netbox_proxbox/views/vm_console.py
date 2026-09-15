"""Standalone Proxmox browser-console tab for NetBox virtual machines."""

from __future__ import annotations

import json

import requests
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, JsonResponse
from django.urls import reverse
from django.views import View
from django.views.decorators.debug import sensitive_variables
from netbox.views import generic
from utilities.views import ViewTab, register_model_view
from virtualization.models import VirtualMachine

from netbox_proxbox.services.vm_console import (
    ConsoleResolutionError,
    browser_websocket_url,
    console_origin,
    resolve_console_backend,
    resolve_console_identity,
)
from netbox_proxbox.views.proxbox_access import (
    permission_enqueue_proxbox_sync,
    permission_open_console,
)

_SESSION_PATH = "proxmox/console/browser-sessions"
_BACKEND_SESSION_FIELDS = {
    "stream_token",
    "websocket_path",
    "expires_at",
    "console_type",
}
_SYNC_REPAIRABLE_CODES = {
    "SYNC_STATE_MISSING",
    "SYNC_ENDPOINT_LINK_MISSING",
    "SYNC_IDENTITY_INCONSISTENT",
    "SYNC_NODE_LINK_INVALID",
    "SYNC_NODE_IDENTITY_DRIFTED",
    "SYNC_CLUSTER_IDENTITY_DRIFTED",
    "SYNC_GUEST_IDENTITY_INCOMPLETE",
}


def _json_error(
    detail: str,
    status: int,
    *,
    code: str | None = None,
    remediation: str | None = None,
) -> JsonResponse:
    payload = {"error": detail}
    if code:
        payload["code"] = code
    if remediation:
        payload["remediation"] = remediation
    return JsonResponse(payload, status=status)


def _console_type(body: object, vm_type: str) -> str:
    if not isinstance(body, dict):
        raise ConsoleResolutionError("Invalid JSON payload.", status=400)
    value = body.get("console_type")
    if value not in {"novnc", "term"}:
        raise ConsoleResolutionError("Unsupported console type.", status=400)
    if vm_type == "lxc" and value != "term":
        raise ConsoleResolutionError(
            "LXC containers support the terminal console only.", status=400
        )
    return str(value)


def _backend_failure_status(status_code: int) -> int:
    if status_code in {400, 403, 404, 409, 422, 429, 503}:
        return status_code
    return 502


def _endpoint_console_permitted(user: object, endpoint: object) -> bool:
    endpoint_scope = type(endpoint).objects.restrict(user, "open_console")
    return endpoint_scope.filter(pk=endpoint.pk, enabled=True).exists()


def _session_payload(
    data: object, *, backend: object, console_type: str
) -> dict[str, str]:
    if (
        not isinstance(data, dict)
        or set(data) != _BACKEND_SESSION_FIELDS
        or data.get("console_type") != console_type
    ):
        raise ConsoleResolutionError(
            "proxbox-api returned an invalid browser-console session.", status=502
        )
    expires_at = data.get("expires_at")
    if not isinstance(expires_at, str) or not expires_at:
        raise ConsoleResolutionError(
            "proxbox-api returned an invalid browser-console session.", status=502
        )
    websocket_url = browser_websocket_url(
        str(getattr(backend, "websocket_base", "")),
        data.get("websocket_path"),
        stream_token=data.get("stream_token"),
    )
    return {
        "websocket_url": websocket_url,
        "stream_token": data["stream_token"],
        "expires_at": expires_at,
        "console_type": console_type,
    }


@register_model_view(VirtualMachine, "proxbox_console", path="console")
class ProxboxVMConsoleTabView(generic.ObjectView):
    """Render the Console tab without contacting Proxmox on page load."""

    queryset = VirtualMachine.objects.all()
    template_name = "netbox_proxbox/vm_console.html"
    tab = ViewTab(
        label="Console",
        permission=permission_open_console(),
        weight=1450,
    )

    def get_required_permission(self) -> str:
        return permission_open_console()

    def has_permission(self) -> bool:
        """Check the endpoint permission without filtering the VM queryset by it."""
        return bool(
            self.request.user.has_perms(
                (self.get_required_permission(), *self.additional_permissions)
            )
        )

    def get_queryset(self, request: HttpRequest) -> object:
        return VirtualMachine.objects.restrict(request.user, "view")

    def get_extra_context(
        self, request: HttpRequest, instance: VirtualMachine
    ) -> dict[str, object]:
        try:
            identity = resolve_console_identity(instance)
        except ConsoleResolutionError as exc:
            can_repair = bool(
                exc.code in _SYNC_REPAIRABLE_CODES
                and request.user.has_perm(permission_enqueue_proxbox_sync())
            )
            return {
                "console_ready": False,
                "detail": exc.detail,
                "error_code": exc.code,
                "remediation": exc.remediation,
                "can_quick_fix": can_repair,
                "quick_fix_url": reverse("plugins:netbox_proxbox:repair_sync_state")
                if can_repair
                else "",
                "vm_type": "",
            }
        if not _endpoint_console_permitted(request.user, identity.endpoint):
            raise PermissionDenied
        return {
            "console_ready": True,
            "detail": None,
            "vm_type": identity.vm_type,
            "session_url": reverse(
                "plugins:netbox_proxbox:virtualmachine_console_session",
                args=[instance.pk],
            ),
        }


class ProxboxVMConsoleSessionView(View):
    """Create one opaque proxbox-api relay session for an authorized VM."""

    http_method_names = ["post"]

    @sensitive_variables()
    def post(self, request: HttpRequest, pk: int) -> JsonResponse:
        if not request.user.is_authenticated:
            return _json_error("Authentication required.", 401)
        if not request.user.has_perm(permission_open_console()):
            return _json_error("Permission denied.", 403)

        vm = VirtualMachine.objects.restrict(request.user, "view").filter(pk=pk).first()
        if vm is None:
            return _json_error("Virtual machine not found.", 404)

        try:
            body = json.loads(request.body.decode() or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            return _json_error("Invalid JSON payload.", 400)

        try:
            identity = resolve_console_identity(vm)
            if not _endpoint_console_permitted(request.user, identity.endpoint):
                return _json_error("Permission denied.", 403)
            selected_console = _console_type(body, identity.vm_type)
            origin = console_origin(request)
            backend = resolve_console_backend(identity)
        except ConsoleResolutionError as exc:
            return _json_error(
                exc.detail,
                exc.status,
                code=exc.code,
                remediation=exc.remediation,
            )

        payload = {
            "endpoint_id": backend.backend_endpoint_id,
            "vmid": identity.vmid,
            "node": identity.node,
            "vm_type": identity.vm_type,
            "console_type": selected_console,
            "origin": origin,
        }
        headers = dict(backend.context.headers)
        headers["X-Proxbox-Actor"] = getattr(request.user, "username", "") or str(
            request.user
        )
        try:
            response = requests.post(
                f"{backend.context.http_url.rstrip('/')}/{_SESSION_PATH}",
                json=payload,
                headers=headers,
                timeout=15,
                verify=backend.context.verify_ssl,
                allow_redirects=False,
            )
        except requests.RequestException:
            return _json_error("The browser-console service is unavailable.", 502)
        if response.status_code != 201:
            return _json_error(
                "The browser-console service refused the session.",
                _backend_failure_status(response.status_code),
            )
        try:
            data = response.json()
            safe_payload = _session_payload(
                data, backend=backend, console_type=selected_console
            )
        except (ValueError, ConsoleResolutionError) as exc:
            detail = (
                exc.detail
                if isinstance(exc, ConsoleResolutionError)
                else "proxbox-api returned an invalid browser-console session."
            )
            return _json_error(detail, 502)
        return JsonResponse(safe_payload)


__all__ = ("ProxboxVMConsoleSessionView", "ProxboxVMConsoleTabView")
