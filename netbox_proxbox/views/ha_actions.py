"""HA arm/disarm operational action views — POST proxies to proxbox-api."""

from __future__ import annotations

import requests
from django.http import HttpRequest, JsonResponse
from django.views import View
from utilities.views import ContentTypePermissionRequiredMixin

from netbox_proxbox.models import ProxmoxEndpoint
from netbox_proxbox.services._endpoint_errors import translate_request_exception
from netbox_proxbox.services.backend_context import get_fastapi_request_context


class _HaActionBaseView(ContentTypePermissionRequiredMixin, View):
    """Base for HA arm/disarm POST actions."""

    _proxbox_action: str  # e.g. "arm" or "disarm"

    def get_required_permission(self) -> str:
        return "netbox_proxbox.change_proxmoxendpoint"

    def post(self, request: HttpRequest) -> JsonResponse:
        ctx = get_fastapi_request_context()
        if ctx is None or not ctx.http_url:
            return JsonResponse(
                {"error": "No FastAPI backend endpoint is configured."}, status=503
            )

        url = f"{ctx.http_url}/proxmox/cluster/ha/{self._proxbox_action}"
        results: list[dict] = []
        for endpoint in ProxmoxEndpoint.objects.filter(enabled=True):
            try:
                resp = requests.post(
                    url,
                    headers=ctx.headers or {},
                    params={"endpoint_id": endpoint.pk},
                    timeout=30,
                    verify=ctx.verify_ssl,
                )
                results.append(
                    {
                        "endpoint_id": endpoint.pk,
                        "endpoint_name": str(endpoint),
                        "status_code": resp.status_code,
                        "ok": resp.ok,
                    }
                )
            except requests.exceptions.RequestException as exc:
                results.append(
                    {
                        "endpoint_id": endpoint.pk,
                        "endpoint_name": str(endpoint),
                        "error": translate_request_exception(exc),
                        "ok": False,
                    }
                )

        return JsonResponse({"action": self._proxbox_action, "results": results})


class HaArmView(_HaActionBaseView):
    """POST — arm HA on all enabled Proxmox endpoints."""

    _proxbox_action = "arm"


class HaDisarmView(_HaActionBaseView):
    """POST — disarm HA on all enabled Proxmox endpoints."""

    _proxbox_action = "disarm"
