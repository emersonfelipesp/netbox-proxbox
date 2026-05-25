"""Check backend, NetBox, Proxmox, and PBS service reachability for the UI."""

from __future__ import annotations

import logging

from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404
from django.views import View

from netbox_proxbox.models import FastAPIEndpoint, NetBoxEndpoint, ProxmoxEndpoint
from netbox_proxbox.services.service_status import ServiceStatus
from utilities.views import TokenConditionalLoginRequiredMixin

logger = logging.getLogger(__name__)

DEPENDENT_SERVICES = ("netbox", "proxmox", "pbs")
KNOWN_SERVICES = ("fastapi", *DEPENDENT_SERVICES)


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


def get_service_status_impl(
    request: HttpRequest, service: str, pk: int
) -> JsonResponse:
    """Build JSON status for fastapi, netbox, proxmox, or pbs service checks."""
    status = "unknown"
    service_status = ServiceStatus()
    pbs_server = None

    if service == "fastapi":
        get_object_or_404(
            FastAPIEndpoint.objects.restrict(request.user, "view"),
            pk=pk,
        )
        fastapi_response = service_status.fastapi_status(pk)
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
        return JsonResponse(payload)

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

    if service == "netbox":
        get_object_or_404(
            NetBoxEndpoint.objects.restrict(request.user, "view"),
            pk=pk,
        )
    elif service == "proxmox":
        get_object_or_404(
            ProxmoxEndpoint.objects.restrict(request.user, "view"),
            pk=pk,
        )
    elif service == "pbs":
        pbs_server = _visible_pbs_server(request, pk)
        if pbs_server is None:
            return JsonResponse(
                {
                    "status": "error",
                    "detail": "netbox-pbs is not installed.",
                },
                status=404,
            )

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

    fastapi_response = service_status.fastapi_status(fastapi_object.id)
    if not fastapi_response.connected:
        return JsonResponse(
            {
                "status": "error",
                "detail": fastapi_response.detail
                or "Unable to connect to configured FastAPI endpoint.",
            },
            status=503,
        )

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

    return JsonResponse(payload)


get_service_status = GetServiceStatusView.as_view()
