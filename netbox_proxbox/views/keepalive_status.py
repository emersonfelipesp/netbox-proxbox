"""Check backend, NetBox, Proxmox, and PBS service reachability for the UI."""

from __future__ import annotations

import hashlib
import json
import logging
import time

from django.db import connection
from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404
from django.views import View

from netbox_proxbox.models import FastAPIEndpoint, NetBoxEndpoint, ProxmoxEndpoint
from netbox_proxbox.services.endpoint_enabled import disabled_endpoint_detail
from netbox_proxbox.services.service_status import ServiceStatus
from netbox_proxbox.utils import (
    get_backend_auth_headers,
    get_fastapi_url,
    get_ip_address_host,
)
from utilities.views import TokenConditionalLoginRequiredMixin

logger = logging.getLogger(__name__)

try:
    from django.core.cache import cache as _django_cache
except (ImportError, ModuleNotFoundError):  # pragma: no cover - lightweight stubs
    _django_cache = None

DEPENDENT_SERVICES = ("netbox", "proxmox", "pbs")
KNOWN_SERVICES = ("fastapi", *DEPENDENT_SERVICES)
FASTAPI_PROBE_SUCCESS_TTL = 30
FASTAPI_PROBE_FAILURE_TTL = 3


def _fastapi_probe_cache_key(endpoint: FastAPIEndpoint) -> str:
    """Key probes by endpoint settings without exposing connection data."""
    url_info = get_fastapi_url(endpoint) or {}
    headers = get_backend_auth_headers(endpoint)
    settings_payload = {
        "url": url_info,
        "headers_hash": hashlib.sha256(
            json.dumps(headers, sort_keys=True).encode()
        ).hexdigest(),
        "enabled": bool(getattr(endpoint, "enabled", True)),
    }
    digest = hashlib.sha256(
        json.dumps(settings_payload, sort_keys=True, default=str).encode()
    ).hexdigest()
    endpoint_id = getattr(endpoint, "pk", getattr(endpoint, "id", "unknown"))
    return f"netbox_proxbox:fastapi_probe:{endpoint_id}:{digest}"


def _cached_fastapi_status(
    service_status: ServiceStatus, endpoint: FastAPIEndpoint
) -> object:
    """Return a short-lived backend probe and restore its connection context."""
    key = _fastapi_probe_cache_key(endpoint)
    cached = _django_cache.get(key) if _django_cache is not None else None
    if isinstance(cached, dict) and cached.get("result") is not None:
        service_status.connected_url = cached.get("connected_url")
        service_status.connected_verify_ssl = bool(cached.get("verify_ssl", True))
        service_status.last_error_detail = cached.get("error_detail")
        service_status.last_error_http_status = cached.get("error_http_status")
        return cached["result"]

    endpoint_id = int(getattr(endpoint, "pk", getattr(endpoint, "id")))
    result = service_status.fastapi_status(endpoint_id)
    timeout = (
        FASTAPI_PROBE_SUCCESS_TTL
        if result.connected and result.api_access != "error"
        else FASTAPI_PROBE_FAILURE_TTL
    )
    if _django_cache is not None:
        _django_cache.set(
            key,
            {
                "result": result,
                "connected_url": service_status.connected_url,
                "verify_ssl": service_status.connected_verify_ssl,
                "error_detail": service_status.last_error_detail,
                "error_http_status": service_status.last_error_http_status,
            },
            timeout=timeout,
        )
    return result


def _throttled_payload(payload: dict[str, object], http_status: int | None) -> None:
    if http_status in {429, 503}:
        payload["status"] = "throttled"


def _visible_pbs_server(request: HttpRequest, pk: int) -> object | None:
    try:
        from netbox_pbs.models import PBSServer  # noqa: PLC0415
    except ImportError:
        return None

    return get_object_or_404(
        PBSServer.objects.restrict(request.user, "view"),
        pk=pk,
    )


class GetServiceStatusView(TokenConditionalLoginRequiredMixin, View):
    """JSON keepalive; object visibility enforced via QuerySet.restrict per service."""

    http_method_names = ["get", "head", "options"]

    def get(self, request: HttpRequest, service: str, pk: int) -> JsonResponse:
        """Dispatch to ``get_service_status_impl`` for the requested service slug."""
        return get_service_status_impl(request, service, pk)


def release_request_db_connection() -> None:
    """Retire the current thread's persistent Django database connection.

    Keepalive polls are the most frequent request the plugin generates, and
    WSGI servers with on-demand worker threads (Granian in netbox-docker) hand
    each poll to a thread that may be reaped 30 seconds later. Django keeps one
    persistent connection per thread for ``CONN_MAX_AGE`` seconds, so a reaped
    thread leaves an idle PostgreSQL connection behind until that age expires.

    The connection is not closed here: closing inside an ``ATOMIC_REQUESTS``
    block marks the transaction broken, and response middleware may still need
    the database. Instead the connection's ``close_at`` deadline is moved to
    now, so Django's own ``request_finished`` handler
    (``close_old_connections``) closes it after the response is complete.
    """
    try:
        if getattr(connection, "in_atomic_block", False):
            logger.debug("Keepalive: inside atomic block; leaving connection open")
            return
        if hasattr(connection, "close_at"):
            connection.close_at = time.monotonic()
            return
        connection.close()
    except Exception:  # noqa: BLE001
        logger.debug("Keepalive: could not retire database connection", exc_info=True)


def get_service_status_impl(
    request: HttpRequest, service: str, pk: int
) -> JsonResponse:
    """Build JSON status for a service and release the DB connection afterwards."""
    try:
        return _build_service_status_response(request, service, pk)
    finally:
        release_request_db_connection()


def _fastapi_status_response(
    request: HttpRequest, pk: int, service_status: ServiceStatus
) -> JsonResponse:
    """Build the keepalive payload for a FastAPI endpoint."""
    fastapi_endpoint = get_object_or_404(
        FastAPIEndpoint.objects.restrict(request.user, "view"),
        pk=pk,
    )
    disabled_detail = disabled_endpoint_detail(
        fastapi_endpoint,
        kind="FastAPI endpoint",
        action="skipping status check",
    )
    if disabled_detail:
        return JsonResponse({"status": "error", "detail": disabled_detail})

    fastapi_response = _cached_fastapi_status(service_status, fastapi_endpoint)
    status = (
        "success"
        if fastapi_response.connected and fastapi_response.api_access != "error"
        else "error"
    )
    payload = {
        "status": status,
        "backend_version": fastapi_response.backend_version,
        "target_address": fastapi_response.target_address,
        "target_port": fastapi_response.target_port,
        "authentication": fastapi_response.authentication,
        "api_access": fastapi_response.api_access,
    }
    if fastapi_response.warnings:
        payload["warnings"] = fastapi_response.warnings
        if not fastapi_response.detail:
            payload["detail"] = " ".join(fastapi_response.warnings)
    if fastapi_response.detail:
        payload["detail"] = fastapi_response.detail
    if fastapi_response.http_status is not None:
        payload["http_status"] = fastapi_response.http_status
    _throttled_payload(payload, fastapi_response.http_status)
    return JsonResponse(payload)


def _resolve_dependent_target(
    request: HttpRequest, service: str, pk: int
) -> tuple[JsonResponse | None, object | None]:
    """Resolve the target object for netbox/proxmox/pbs checks.

    Returns an early ``JsonResponse`` when the target is missing or disabled,
    otherwise ``(None, pbs_server)`` where ``pbs_server`` is set only for PBS.
    """
    if service == "netbox":
        netbox_endpoint = get_object_or_404(
            NetBoxEndpoint.objects.restrict(request.user, "view"),
            pk=pk,
        )
        disabled_detail = disabled_endpoint_detail(
            netbox_endpoint, kind="NetBox endpoint", action="skipping status check"
        )
        if disabled_detail:
            return JsonResponse({"status": "error", "detail": disabled_detail}), None
        return None, None

    if service == "proxmox":
        proxmox_endpoint = get_object_or_404(
            ProxmoxEndpoint.objects.restrict(request.user, "view"),
            pk=pk,
        )
        disabled_detail = disabled_endpoint_detail(
            proxmox_endpoint,
            kind="Proxmox endpoint",
            action="skipping status check",
        )
        if disabled_detail:
            return (
                JsonResponse(
                    {
                        "status": "disabled",
                        "detail": disabled_detail,
                        "target_address": getattr(proxmox_endpoint, "domain", None)
                        or get_ip_address_host(
                            getattr(proxmox_endpoint, "ip_address", None)
                        ),
                        "target_port": getattr(proxmox_endpoint, "port", None) or 8006,
                        "authentication": "disabled",
                        "api_access": "disabled",
                    }
                ),
                None,
            )
        return None, None

    pbs_server = _visible_pbs_server(request, pk)
    if pbs_server is None:
        return (
            JsonResponse(
                {"status": "error", "detail": "netbox-pbs is not installed."},
                status=404,
            ),
            None,
        )
    disabled_detail = disabled_endpoint_detail(
        pbs_server, kind="PBS endpoint", action="skipping status check"
    )
    if disabled_detail:
        return JsonResponse({"status": "error", "detail": disabled_detail}), None
    return None, pbs_server


def _build_service_status_response(
    request: HttpRequest, service: str, pk: int
) -> JsonResponse:
    """Build JSON status for fastapi, netbox, proxmox, or pbs service checks."""
    status = "unknown"
    service_status = ServiceStatus()

    if service == "fastapi":
        return _fastapi_status_response(request, pk, service_status)

    if service not in DEPENDENT_SERVICES:
        return JsonResponse(
            {
                "status": "error",
                "detail": (
                    f"Unknown service {service!r}. "
                    f"Expected {', '.join(KNOWN_SERVICES[:-1])}, or {KNOWN_SERVICES[-1]}."
                ),
            },
            status=400,
        )

    early_response, pbs_server = _resolve_dependent_target(request, service, pk)
    if early_response is not None:
        return early_response

    fastapi_object = (
        FastAPIEndpoint.objects.restrict(request.user, "view")
        .filter(enabled=True)
        .first()
    )
    if fastapi_object is None:
        logger.error("No FastAPI endpoints found")
        return JsonResponse(
            {
                "status": "error",
                "detail": "No FastAPI endpoint is configured.",
            },
            status=503,
        )

    fastapi_response = _cached_fastapi_status(service_status, fastapi_object)
    if not fastapi_response.connected:
        payload = {
            "status": "error",
            "detail": fastapi_response.detail
            or "Unable to connect to configured FastAPI endpoint.",
        }
        if fastapi_response.http_status is not None:
            payload["http_status"] = fastapi_response.http_status
        _throttled_payload(payload, fastapi_response.http_status)
        return JsonResponse(payload, status=503)

    auth_headers = service_status.backend_auth_headers(fastapi_object)

    if not service_status.connected_url:
        logger.error(
            "FastAPI connectivity reported success but no connected URL was recorded"
        )
        return JsonResponse(
            {
                "status": "error",
                "detail": "FastAPI endpoint responded, but no connected URL was recorded.",
            },
            status=503,
        )

    connected_url = service_status.connected_url

    if service == "netbox":
        status, details = service_status.netbox_status(
            pk=pk,
            base_url=connected_url,
            auth_headers=auth_headers,
        )
    elif service == "proxmox":
        status, details = service_status.proxmox_status(
            pk=pk,
            base_url=connected_url,
            auth_headers=auth_headers,
            backend_verify_ssl=service_status.connected_verify_ssl,
        )
    elif service == "pbs" and pbs_server is not None:
        status, details = service_status.pbs_status(
            endpoint=pbs_server,
            base_url=connected_url,
            auth_headers=auth_headers,
            backend_verify_ssl=service_status.connected_verify_ssl,
        )

    payload = {
        "status": status,
        "target_address": details.target_address,
        "target_port": details.target_port,
        "authentication": details.authentication,
        "api_access": details.api_access,
    }
    if status != "success" and service_status.last_error_detail:
        payload["detail"] = service_status.last_error_detail
    if status != "success" and service_status.last_error_http_status is not None:
        payload["http_status"] = service_status.last_error_http_status
    _throttled_payload(payload, service_status.last_error_http_status)

    return JsonResponse(payload)


get_service_status = GetServiceStatusView.as_view()
