"""Dashboard view for Proxmox cluster and node operational summaries."""

from __future__ import annotations

import requests
from django.contrib.auth.mixins import AccessMixin
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views import View
from utilities.views import ConditionalLoginRequiredMixin
from virtualization.models import Cluster

import netbox_proxbox.views.dashboard_data as dashboard_data
from netbox_proxbox.models import FastAPIEndpoint, ProxmoxEndpoint, ProxmoxNode
from netbox_proxbox.utils import get_backend_auth_headers, get_fastapi_url
from netbox_proxbox.views.backend_sync import (
    resolve_backend_endpoint_id,
    sync_proxmox_endpoint_to_backend,
)
from netbox_proxbox.views.error_utils import (
    extract_proxmox_backend_error_detail,
    parse_requests_response_json,
)
from netbox_proxbox.views.proxbox_access import user_may_access_proxbox_dashboard

__all__ = ("DashboardView", "ProxmoxNode")


class RequireProxboxDashboardAccessMixin(AccessMixin):
    """Require view permission on at least one endpoint model when authenticated."""

    def dispatch(
        self, request: HttpRequest, *args: object, **kwargs: object
    ) -> HttpResponse:
        """Handle dispatch."""
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

    def _endpoint_query_params(self, backend_endpoint_id: int) -> dict[str, str]:
        return {
            "source": "database",
            "proxmox_endpoint_ids": str(backend_endpoint_id),
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

    def get(self, request: HttpRequest) -> HttpResponse:
        """Handle get."""
        dashboard_data.ProxmoxNode = ProxmoxNode
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

            backend_endpoint_id, resolve_error = resolve_backend_endpoint_id(
                endpoint,
                base_url=fastapi_url,
                auth_headers=backend_headers,
                backend_verify_ssl=backend_verify_ssl,
                timeout=self.request_timeout,
            )
            if backend_endpoint_id is None:
                dashboard["detail"] = (
                    resolve_error
                    or "Failed to resolve Proxmox endpoint on ProxBox backend."
                )
                dashboards.append(dashboard)
                continue

            query_params = self._endpoint_query_params(backend_endpoint_id)

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
                continue

            cluster_name = None
            cluster_node_names: set[str] = set()
            if not cluster_err:
                cluster_name, cluster_node_names = dashboard_data.cluster_node_scope(
                    cluster_payload
                )

            local_node_rows = dashboard_data.build_local_node_rows(
                endpoint,
                cluster_name=cluster_name,
                cluster_node_names=cluster_node_names,
            )
            live_node_rows: list[dict[str, object]] = []
            nodes_err = None
            try:
                nodes_payload, nodes_err = self._fetch_json(
                    base_url=fastapi_url,
                    auth_headers=backend_headers,
                    verify_ssl=backend_verify_ssl,
                    route="/proxmox/nodes/",
                    query_params=query_params,
                )
                if not nodes_err:
                    live_node_rows = dashboard_data.build_live_node_rows(nodes_payload)
            except requests.exceptions.RequestException as exc:
                if not local_node_rows:
                    detail, _ = extract_proxmox_backend_error_detail(
                        exc,
                        proxmox_host=endpoint.domain
                        or str(endpoint.ip_address).split("/")[0],
                        proxmox_port=endpoint.port,
                        backend_url=f"{fastapi_url}/proxmox",
                    )
                    dashboard["detail"] = detail
                    dashboards.append(dashboard)
                    continue

            if cluster_err or resources_err:
                dashboard["detail"] = cluster_err or resources_err
                dashboards.append(dashboard)
                continue

            if nodes_err and not local_node_rows:
                dashboard["detail"] = nodes_err
                dashboards.append(dashboard)
                continue

            cluster_summary = dashboard_data.build_cluster_summary(cluster_payload)
            dashboard["guest_summary"] = dashboard_data.build_guest_summary(
                resources_payload
            )
            if local_node_rows:
                dashboard["nodes"] = dashboard_data.merge_node_rows(
                    local_node_rows, live_node_rows
                )
            else:
                dashboard["nodes"] = live_node_rows
            dashboard["cluster_summary"] = (
                dashboard_data.cluster_summary_from_node_rows(
                    cluster_summary, dashboard["nodes"]
                )
            )
            dashboard["nodes"] = dashboard_data.append_unsynced_node_placeholders(
                dashboard["nodes"], cluster_node_names
            )

            dashboard["endpoint_ip"] = dashboard_data.get_endpoint_display_ip(endpoint)

            cluster_name = (
                dashboard["cluster_summary"].get("name", "")
                if dashboard["cluster_summary"]
                else ""
            )
            if cluster_name and cluster_name != "—":
                netbox_cluster = Cluster.objects.filter(name=cluster_name).first()
            else:
                netbox_cluster = None
            dashboard["netbox_cluster"] = netbox_cluster
            dashboard["object_summaries"] = dashboard_data.build_object_summaries(
                endpoint, netbox_cluster
            )

            dashboards.append(dashboard)

        return render(
            request,
            self.template_name,
            {
                "dashboards": dashboards,
            },
        )
