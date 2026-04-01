"""Dashboard view for Proxmox cluster and node operational summaries."""

from __future__ import annotations

import requests
from django.contrib.auth.mixins import AccessMixin
from django.shortcuts import render
from django.views import View
from virtualization.models import Cluster

from netbox_proxbox.models import FastAPIEndpoint, ProxmoxEndpoint
from netbox_proxbox.schemas import (
    ProxmoxClusterStatusResponse,
    ProxmoxClusterSummary,
    ProxmoxGuestSummary,
    ProxmoxNodeDetail,
    ProxmoxNodeRow,
    ProxmoxResourceRecord,
)
from netbox_proxbox.schemas._formatters import iter_scalar_records
from netbox_proxbox.utils import get_backend_auth_headers, get_fastapi_url
from netbox_proxbox.views.backend_sync import sync_proxmox_endpoint_to_backend
from netbox_proxbox.views.error_utils import (
    extract_proxmox_backend_error_detail,
    parse_requests_response_json,
)
from netbox_proxbox.views.proxbox_access import user_may_access_proxbox_dashboard
from utilities.views import ConditionalLoginRequiredMixin

__all__ = ("DashboardView",)


def _get_endpoint_display_ip(endpoint: ProxmoxEndpoint) -> str:
    """Return the display IP address for an endpoint."""
    if endpoint.domain:
        return endpoint.domain
    if endpoint.ip_address:
        return str(endpoint.ip_address.address).split("/")[0]
    return "—"


class RequireProxboxDashboardAccessMixin(AccessMixin):
    """Require view permission on at least one endpoint model when authenticated."""

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not user_may_access_proxbox_dashboard(
            request.user
        ):
            return self.handle_no_permission()
        return super().dispatch(request, *args, **kwargs)


class DashboardView(
    ConditionalLoginRequiredMixin,
    RequireProxboxDashboardAccessMixin,
    View,
):
    """Render cluster and node summaries using proxbox-api data."""

    template_name = "netbox_proxbox/dashboard.html"
    request_timeout = 8

    def _endpoint_query_params(self, endpoint: ProxmoxEndpoint) -> dict[str, str]:
        domain = (endpoint.domain or "").strip()
        if domain:
            return {"source": "database", "domain": domain}
        return {
            "source": "database",
            "ip_address": str(endpoint.ip_address).split("/")[0],
        }

    def _fetch_json(
        self,
        *,
        base_url: str,
        auth_headers: dict[str, str],
        verify_ssl: bool,
        route: str,
        query_params: dict[str, str],
    ) -> tuple[object | None, str | None]:
        response = requests.get(
            f"{base_url}{route}",
            params=query_params,
            headers=auth_headers,
            verify=verify_ssl,
            timeout=self.request_timeout,
        )
        response.raise_for_status()
        payload, json_err = parse_requests_response_json(response, log_label=route)
        return payload, json_err

    def _build_cluster_summary(self, cluster_payload: object) -> dict[str, object]:
        response = ProxmoxClusterStatusResponse.model_validate(cluster_payload)
        return ProxmoxClusterSummary.from_status_response(response).model_dump()

    def _build_guest_summary(self, resources_payload: object) -> dict[str, object]:
        resource_records = [
            ProxmoxResourceRecord.model_validate(record)
            for record in iter_scalar_records(resources_payload)
        ]
        return ProxmoxGuestSummary.from_resources(resource_records).model_dump()

    def _build_node_rows(self, nodes_payload: object) -> list[dict[str, object]]:
        rows = [
            ProxmoxNodeRow.from_node_detail(
                ProxmoxNodeDetail.model_validate(record)
            ).model_dump()
            for record in iter_scalar_records(nodes_payload)
        ]
        return sorted(rows, key=lambda row: str(row["name"]))

    def get(self, request):
        proxmox_endpoints = list(ProxmoxEndpoint.objects.restrict(request.user, "view"))
        fastapi_endpoint = FastAPIEndpoint.objects.restrict(
            request.user, "view"
        ).first()

        dashboards: list[dict[str, object]] = []
        if fastapi_endpoint:
            fastapi_info = get_fastapi_url(fastapi_endpoint) or {}
            fastapi_url = fastapi_info.get("http_url")
            backend_verify_ssl = bool(fastapi_info.get("verify_ssl", True))
            backend_headers = get_backend_auth_headers(fastapi_endpoint)
        else:
            fastapi_url = None
            backend_verify_ssl = True
            backend_headers = {}

        for endpoint in proxmox_endpoints:
            dashboard: dict[str, object] = {
                "endpoint": endpoint,
                "cluster_summary": None,
                "guest_summary": None,
                "nodes": [],
                "detail": None,
            }

            if not fastapi_url:
                dashboard["detail"] = "No FastAPI backend URL is configured."
                dashboards.append(dashboard)
                continue

            sync_ok, sync_detail, _ = sync_proxmox_endpoint_to_backend(
                endpoint,
                base_url=fastapi_url,
                auth_headers=backend_headers,
                backend_verify_ssl=backend_verify_ssl,
                timeout=self.request_timeout,
            )
            if not sync_ok:
                dashboard["detail"] = sync_detail
                dashboards.append(dashboard)
                continue

            query_params = self._endpoint_query_params(endpoint)

            try:
                cluster_payload, cluster_err = self._fetch_json(
                    base_url=fastapi_url,
                    auth_headers=backend_headers,
                    verify_ssl=backend_verify_ssl,
                    route="/proxmox/cluster/status",
                    query_params=query_params,
                )
                resources_payload, resources_err = self._fetch_json(
                    base_url=fastapi_url,
                    auth_headers=backend_headers,
                    verify_ssl=backend_verify_ssl,
                    route="/proxmox/cluster/resources",
                    query_params=query_params,
                )
                nodes_payload, nodes_err = self._fetch_json(
                    base_url=fastapi_url,
                    auth_headers=backend_headers,
                    verify_ssl=backend_verify_ssl,
                    route="/proxmox/nodes/",
                    query_params=query_params,
                )
                if cluster_err or resources_err or nodes_err:
                    dashboard["detail"] = cluster_err or resources_err or nodes_err
                else:
                    dashboard["cluster_summary"] = self._build_cluster_summary(
                        cluster_payload
                    )
                    dashboard["guest_summary"] = self._build_guest_summary(
                        resources_payload
                    )
                    dashboard["nodes"] = self._build_node_rows(nodes_payload)

                    # Add endpoint IP for display
                    dashboard["endpoint_ip"] = _get_endpoint_display_ip(endpoint)

                    # Try to match with NetBox Cluster
                    cluster_name = (
                        dashboard["cluster_summary"].get("name", "")
                        if dashboard["cluster_summary"]
                        else ""
                    )
                    if cluster_name and cluster_name != "—":
                        netbox_cluster = Cluster.objects.filter(
                            name=cluster_name
                        ).first()
                    else:
                        netbox_cluster = None
                    dashboard["netbox_cluster"] = netbox_cluster
            except requests.exceptions.RequestException as exc:
                detail, _ = extract_proxmox_backend_error_detail(
                    exc,
                    proxmox_host=endpoint.domain
                    or str(endpoint.ip_address).split("/")[0],
                    proxmox_port=endpoint.port,
                    backend_url=f"{fastapi_url}/proxmox",
                )
                dashboard["detail"] = detail

            dashboards.append(dashboard)

        return render(
            request,
            self.template_name,
            {
                "dashboards": dashboards,
            },
        )
