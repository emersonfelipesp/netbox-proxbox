"""Check backend, NetBox, and Proxmox service reachability for the plugin UI."""

from __future__ import annotations

import logging
from typing import Any

from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404
from django.views import View

from netbox_proxbox.models import FastAPIEndpoint, NetBoxEndpoint, ProxmoxEndpoint
from netbox_proxbox.services.service_status import ServiceStatus
from utilities.views import TokenConditionalLoginRequiredMixin

logger = logging.getLogger(__name__)


class GetServiceStatusView(TokenConditionalLoginRequiredMixin, View):
    """JSON keepalive; object visibility enforced via QuerySet.restrict per service."""

    http_method_names = ["get", "head", "options"]

    def get(self, request: HttpRequest, service: str, pk: int) -> JsonResponse:
        return get_service_status_impl(request, service, pk)


def get_service_status_impl(
    request: HttpRequest, service: str, pk: int
) -> JsonResponse:
    """Build JSON status for fastapi, netbox, or proxmox service checks."""
    status = "unknown"
    service_status = ServiceStatus()

    if service == "fastapi":
        get_object_or_404(
            FastAPIEndpoint.objects.restrict(request.user, "view"),
            pk=pk,
        )
        fastapi_response = service_status.fastapi_status(pk)
        status = "success" if fastapi_response.get("connected") else "error"
        payload: dict[str, Any] = {"status": status}
        if fastapi_response.get("detail"):
            payload["detail"] = fastapi_response["detail"]
        return JsonResponse(payload)

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

    fastapi_object = FastAPIEndpoint.objects.restrict(request.user, "view").first()
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
    if not fastapi_response.get("connected"):
        return JsonResponse(
            {
                "status": "error",
                "detail": fastapi_response.get("detail")
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
        status = service_status.netbox_status(
            pk=pk,
            base_url=connected_url,
            auth_headers=auth_headers,
        )
    elif service == "proxmox":
        status = service_status.proxmox_status(
            pk=pk,
            base_url=connected_url,
            auth_headers=auth_headers,
            backend_verify_ssl=service_status.connected_verify_ssl,
        )

    payload = {"status": status}
    if status != "success" and service_status.last_error_detail:
        payload["detail"] = service_status.last_error_detail
    if status != "success" and service_status.last_error_http_status is not None:
        payload["http_status"] = service_status.last_error_http_status

    return JsonResponse(payload)


get_service_status = GetServiceStatusView.as_view()
