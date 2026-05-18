"""Cluster-wide HA dashboard fetching live data from proxbox-api."""

from __future__ import annotations

import requests
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views import View
from utilities.views import ConditionalLoginRequiredMixin

from netbox_proxbox.services._endpoint_errors import translate_request_exception
from netbox_proxbox.services.backend_context import get_fastapi_request_context
from netbox_proxbox.views.proxbox_access import RequireProxboxDashboardAccessMixin


class HAClusterView(
    ConditionalLoginRequiredMixin,
    RequireProxboxDashboardAccessMixin,
    View,
):
    """Render an aggregated cluster-wide HA status page."""

    template_name = "netbox_proxbox/ha.html"

    def get(self, request: HttpRequest) -> HttpResponse:
        context: dict[str, object] = {
            "summary": None,
            "detail": None,
        }

        ctx = get_fastapi_request_context()
        if ctx is None or not ctx.http_url:
            context["detail"] = "No FastAPI backend endpoint is configured."
            return render(request, self.template_name, context)

        url = f"{ctx.http_url}/proxmox/cluster/ha/summary"
        try:
            response = requests.get(
                url,
                headers=ctx.headers or {},
                timeout=15,
                verify=ctx.verify_ssl,
            )
            if response.status_code == 404:
                context["detail"] = (
                    "Backend does not support HA endpoints — "
                    "upgrade proxbox-api to v0.0.12 or later."
                )
                return render(request, self.template_name, context)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                context["detail"] = "Unexpected HA summary payload from backend."
                return render(request, self.template_name, context)
            context["summary"] = payload
        except requests.exceptions.RequestException as exc:
            context["detail"] = translate_request_exception(exc)
        except ValueError as exc:
            context["detail"] = f"Invalid HA payload from backend: {exc}"

        return render(request, self.template_name, context)
