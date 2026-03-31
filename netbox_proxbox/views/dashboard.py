"""Dashboard view for Proxmox cluster and node operational summaries."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import requests
from django.contrib.auth.mixins import AccessMixin
from django.shortcuts import render
from django.views import View

from netbox_proxbox.models import FastAPIEndpoint, ProxmoxEndpoint
from netbox_proxbox.utils import get_backend_auth_headers, get_fastapi_url
from netbox_proxbox.views.backend_sync import sync_proxmox_endpoint_to_backend
from netbox_proxbox.views.error_utils import (
    extract_proxmox_backend_error_detail,
    parse_requests_response_json,
)
from netbox_proxbox.views.proxbox_access import user_may_access_proxbox_dashboard
from utilities.views import ConditionalLoginRequiredMixin

__all__ = ("DashboardView",)


def _iter_scalar_records(payload: Any) -> Iterable[dict[str, Any]]:
    """Yield flattened dictionary records from nested list/dict payloads."""
    if isinstance(payload, list):
        for item in payload:
            yield from _iter_scalar_records(item)
        return

    if isinstance(payload, dict):
        has_nested = any(isinstance(v, (dict, list)) for v in payload.values())
        if not has_nested:
            yield payload
            return
        for value in payload.values():
            yield from _iter_scalar_records(value)


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _percent(value: Any, max_value: Any) -> float:
    val = _to_float(value)
    max_val = _to_float(max_value)
    if max_val <= 0:
        return 0.0
    return round((val / max_val) * 100.0, 2)


def _cpu_percent(value: Any) -> float:
    cpu = _to_float(value)
    if cpu <= 1:
        return round(cpu * 100.0, 2)
    return round(cpu, 2)


def _format_bytes(value: Any) -> str:
    size = float(_to_int(value))
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    unit_idx = 0
    while size >= 1024 and unit_idx < len(units) - 1:
        size /= 1024
        unit_idx += 1
    return f"{size:.2f} {units[unit_idx]}"


def _format_uptime(seconds: Any) -> str:
    total = _to_int(seconds)
    if total <= 0:
        return "—"
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{days}d {hours:02}:{minutes:02}:{secs:02}"


def _loadavg_text(value: Any) -> str:
    if isinstance(value, (list, tuple)) and value:
        return ", ".join(f"{_to_float(v):.2f}" for v in value[:3])
    if isinstance(value, str) and value.strip():
        return value.strip()
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
    ) -> tuple[Any | None, str | None]:
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

    def _build_cluster_summary(self, cluster_payload: Any) -> dict[str, Any]:
        records = list(_iter_scalar_records(cluster_payload))
        cluster_record = next((r for r in records if r.get("type") == "cluster"), {})
        node_records = [r for r in records if r.get("type") == "node"]

        total_nodes = _to_int(cluster_record.get("nodes"), default=len(node_records))
        online_nodes = sum(_to_int(r.get("online")) for r in node_records)
        if online_nodes == 0:
            online_nodes = sum(
                1 for r in node_records if str(r.get("status")) == "online"
            )
        offline_nodes = max(total_nodes - online_nodes, 0)

        return {
            "name": cluster_record.get("name") or "—",
            "mode": cluster_record.get("level") or cluster_record.get("type") or "—",
            "quorate": bool(cluster_record.get("quorate")),
            "nodes_total": total_nodes,
            "nodes_online": online_nodes,
            "nodes_offline": offline_nodes,
        }

    def _build_guest_summary(self, resources_payload: Any) -> dict[str, dict[str, int]]:
        records = list(_iter_scalar_records(resources_payload))
        qemu_records = [r for r in records if str(r.get("type")) == "qemu"]
        lxc_records = [r for r in records if str(r.get("type")) == "lxc"]

        def _count(items: list[dict[str, Any]]) -> dict[str, int]:
            running = sum(1 for r in items if str(r.get("status")) == "running")
            templates = sum(1 for r in items if bool(r.get("template")))
            stopped = max(len(items) - running - templates, 0)
            return {
                "running": running,
                "stopped": stopped,
                "templates": templates,
            }

        return {
            "virtual_machines": _count(qemu_records),
            "lxc_containers": _count(lxc_records),
        }

    def _build_node_rows(self, nodes_payload: Any) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for record in _iter_scalar_records(nodes_payload):
            node_name = record.get("node") or record.get("name")
            if not node_name:
                continue
            mem_used = _to_int(record.get("mem"))
            mem_total = _to_int(record.get("maxmem"))
            disk_used = _to_int(record.get("disk"))
            disk_total = _to_int(record.get("maxdisk"))
            cpu_pct = _cpu_percent(record.get("cpu"))
            mem_pct = _percent(mem_used, mem_total)
            disk_pct = _percent(disk_used, disk_total)
            rows.append(
                {
                    "name": str(node_name),
                    "status": str(record.get("status") or "unknown"),
                    "uptime": _format_uptime(record.get("uptime")),
                    "cpu_pct": cpu_pct,
                    "cpu_label": f"{cpu_pct:.2f}% ({_to_int(record.get('maxcpu'))} CPUs)",
                    "loadavg": _loadavg_text(record.get("loadavg")),
                    "memory_pct": mem_pct,
                    "memory_label": f"{_format_bytes(mem_used)} / {_format_bytes(mem_total)}",
                    "disk_pct": disk_pct,
                    "disk_label": f"{_format_bytes(disk_used)} / {_format_bytes(disk_total)}",
                }
            )
        return sorted(rows, key=lambda row: row["name"])

    def get(self, request):
        proxmox_endpoints = list(ProxmoxEndpoint.objects.restrict(request.user, "view"))
        fastapi_endpoint = FastAPIEndpoint.objects.restrict(
            request.user, "view"
        ).first()

        dashboards: list[dict[str, Any]] = []
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
            dashboard: dict[str, Any] = {
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
