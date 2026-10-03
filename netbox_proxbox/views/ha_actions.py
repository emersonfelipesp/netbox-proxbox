"""HA arm/disarm operational action views — POST proxies to proxbox-api.

Arm/disarm is an operational Proxmox write, so it follows the same trust
boundary as the other operational verbs (see ``views/operational.py``):

* the caller needs the ``run_proxmox_action`` action on Proxmox endpoints, a
  custom NetBox object-permission action that can be granted to non-superusers
  and constrained to specific endpoints;
* only endpoints the caller holds that action on are in scope;
* endpoints with ``allow_writes`` disabled are reported as skipped and are
  never sent to the backend. proxbox-api enforces the same flag; this is
  defence in depth.
"""

from __future__ import annotations

from typing import ClassVar

import requests
from django.db.models import QuerySet
from django.http import HttpRequest, JsonResponse
from django.views import View
from utilities.views import ContentTypePermissionRequiredMixin

from netbox_proxbox.models import ProxmoxEndpoint
from netbox_proxbox.schemas.backend_proxy import BackendRequestContext
from netbox_proxbox.services._endpoint_errors import translate_request_exception
from netbox_proxbox.services.backend_context import get_fastapi_request_context
from netbox_proxbox.services.endpoint_scope import enabled_backend_endpoint_scope
from netbox_proxbox.views.proxbox_access import (
    ENDPOINT_OPERATIONAL_ACTION,
    permission_run_endpoint_action,
)

_BACKEND_TIMEOUT_S = 30
WRITES_DISABLED_ERROR = "endpoint_writes_disabled"


class _InvalidEndpointSelection(Exception):
    """Raised when the optional ``endpoint_id`` POST field is malformed."""


def _requested_endpoint_id(request: HttpRequest) -> int | None:
    """Return the optional ``endpoint_id`` POST field as a positive integer."""
    raw = str(request.POST.get("endpoint_id", "") or "").strip()
    if not raw:
        return None
    if not (raw.isascii() and raw.isdigit()) or len(raw) > 18 or int(raw) < 1:
        raise _InvalidEndpointSelection(raw)
    return int(raw)


def _ha_body_succeeded(body: object) -> bool:
    """Return whether proxbox-api reported success for every HA operation.

    proxbox-api answers HTTP 200 even when Proxmox rejects the command and
    reports the failure per cluster as ``{"status": "error", ...}``. An empty
    or malformed body is not evidence of success.
    """
    if not isinstance(body, list) or not body:
        return False
    return all(
        isinstance(row, dict) and str(row.get("status", "")).lower() == "ok"
        for row in body
    )


def _endpoint_result(endpoint: ProxmoxEndpoint, **fields: object) -> dict:
    """Build one per-endpoint result row."""
    return {"endpoint_id": endpoint.pk, "endpoint_name": str(endpoint), **fields}


class _HaActionBaseView(ContentTypePermissionRequiredMixin, View):
    """Base for HA arm/disarm POST actions.

    Session authentication only (CSRF-protected). API tokens are deliberately
    not accepted here: NetBox's token mixin does not enforce a token's
    ``write_enabled`` flag, so a read-only token could otherwise drive a write.
    """

    _proxbox_action: str  # e.g. "arm" or "disarm"
    http_method_names: ClassVar[list[str]] = ["post"]

    def get_required_permission(self) -> str:
        """Require the grantable operational action on Proxmox endpoints."""
        return permission_run_endpoint_action()

    @staticmethod
    def _scoped_endpoints(
        request: HttpRequest, endpoint_id: int | None
    ) -> QuerySet[ProxmoxEndpoint]:
        """Return enabled endpoints the caller may change, optionally one of them."""
        queryset = ProxmoxEndpoint.objects.restrict(
            request.user, ENDPOINT_OPERATIONAL_ACTION
        ).filter(enabled=True)
        if endpoint_id is not None:
            queryset = queryset.filter(pk=endpoint_id)
        return queryset.order_by("pk")

    def _post_endpoint(
        self,
        url: str,
        endpoint: ProxmoxEndpoint,
        backend_endpoint_id: int,
        ctx: BackendRequestContext,
    ) -> dict:
        """Send the HA verb for one endpoint and describe the outcome."""
        try:
            resp = requests.post(
                url,
                headers=ctx.headers or {},
                params={"proxmox_endpoint_ids": str(backend_endpoint_id)},
                timeout=_BACKEND_TIMEOUT_S,
                verify=ctx.verify_ssl,
                allow_redirects=False,
            )
        except requests.exceptions.RequestException as exc:
            return _endpoint_result(
                endpoint, error=translate_request_exception(exc), ok=False
            )
        try:
            body = resp.json()
        except Exception:
            body = None
        return _endpoint_result(
            endpoint,
            status_code=resp.status_code,
            ok=bool(resp.ok) and _ha_body_succeeded(body),
            body=body,
        )

    def post(self, request: HttpRequest) -> JsonResponse:
        """Arm or disarm HA on the permitted, write-enabled endpoints."""
        try:
            endpoint_id = _requested_endpoint_id(request)
        except _InvalidEndpointSelection:
            return JsonResponse(
                {"error": "endpoint_id must be an integer."}, status=400
            )

        endpoints = list(self._scoped_endpoints(request, endpoint_id))
        if endpoint_id is not None and not endpoints:
            return JsonResponse({"error": "Proxmox endpoint not found."}, status=404)

        ctx = get_fastapi_request_context()
        if ctx is None or not ctx.http_url:
            return JsonResponse(
                {"error": "No FastAPI backend endpoint is configured."}, status=503
            )

        writable = [endpoint for endpoint in endpoints if endpoint.allow_writes]
        results: list[dict] = [
            _endpoint_result(endpoint, error=WRITES_DISABLED_ERROR, ok=False)
            for endpoint in endpoints
            if not endpoint.allow_writes
        ]
        if writable:
            dispatched, scope_error = self._dispatch_writable(ctx, writable)
            if scope_error:
                return JsonResponse(
                    {"action": self._proxbox_action, "error": scope_error}, status=502
                )
            results.extend(dispatched)
        return JsonResponse({"action": self._proxbox_action, "results": results})

    def _dispatch_writable(
        self, ctx: BackendRequestContext, writable: list[ProxmoxEndpoint]
    ) -> tuple[list[dict], str | None]:
        """Resolve backend ids for ``writable`` and send the HA verb to each."""
        _, backend_id_by_pk, scope_error = enabled_backend_endpoint_scope(
            base_url=ctx.http_url,
            auth_headers=ctx.headers or {},
            backend_verify_ssl=ctx.verify_ssl,
            timeout=_BACKEND_TIMEOUT_S,
            endpoint_ids=[endpoint.pk for endpoint in writable],
        )
        if scope_error:
            return [], scope_error
        url = f"{ctx.http_url}/proxmox/cluster/ha/{self._proxbox_action}"
        results: list[dict] = []
        for endpoint in writable:
            backend_endpoint_id = backend_id_by_pk.get(endpoint.pk)
            if backend_endpoint_id is None:
                results.append(
                    _endpoint_result(
                        endpoint, error="Backend endpoint id not resolved.", ok=False
                    )
                )
                continue
            results.append(self._post_endpoint(url, endpoint, backend_endpoint_id, ctx))
        return results, None


class HaArmView(_HaActionBaseView):
    """POST — arm HA on the caller's permitted, write-enabled Proxmox endpoints."""

    _proxbox_action = "arm"


class HaDisarmView(_HaActionBaseView):
    """POST — disarm HA on the caller's permitted, write-enabled Proxmox endpoints."""

    _proxbox_action = "disarm"
