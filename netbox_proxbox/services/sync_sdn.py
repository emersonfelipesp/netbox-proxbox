"""Sync service for Proxmox SDN objects from proxbox-api.

Calls the SDN endpoints on proxbox-api:
  - GET /proxmox/sdn/fabrics
  - GET /proxmox/sdn/route-maps
  - GET /proxmox/sdn/prefix-lists

Results are upserted into the three SDN Django models.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

import requests
from django.db import transaction

from netbox_proxbox.choices import FirewallSyncStatusChoices
from netbox_proxbox.models import (
    ProxmoxEndpoint,
    ProxmoxSdnFabric,
    ProxmoxSdnPrefixList,
    ProxmoxSdnRouteMap,
)
from netbox_proxbox.services.backend_proxy import get_fastapi_request_context
from netbox_proxbox.services.endpoint_scope import enabled_backend_endpoint_scope

logger = logging.getLogger(__name__)

SYNC_TIMEOUT = 30


@dataclass
class SdnSyncResult:
    success: bool = False
    error: str | None = None
    endpoints_processed: int = 0
    fabrics_created: int = 0
    fabrics_updated: int = 0
    fabrics_stale: int = 0
    route_maps_created: int = 0
    route_maps_updated: int = 0
    route_maps_stale: int = 0
    prefix_lists_created: int = 0
    prefix_lists_updated: int = 0
    prefix_lists_stale: int = 0
    per_endpoint: list[dict] = field(default_factory=list)


def _resolve_endpoint_by_cluster_name(cluster_name: str) -> ProxmoxEndpoint | None:
    try:
        from netbox_proxbox.models import ProxmoxCluster  # noqa: PLC0415

        cluster = (
            ProxmoxCluster.objects.filter(name=cluster_name)
            .select_related("endpoint")
            .first()
        )
        if (
            cluster
            and cluster.endpoint_id
            and bool(getattr(cluster.endpoint, "enabled", True))
        ):
            return cluster.endpoint
    except Exception as exc:
        logger.warning("DB error resolving cluster %r: %s", cluster_name, exc)
    return ProxmoxEndpoint.objects.filter(name=cluster_name, enabled=True).first()


def _upsert_fabric(endpoint: ProxmoxEndpoint, item: dict, result: SdnSyncResult) -> int:
    cluster_name = item.get("cluster_name", "")
    fabric_name = item.get("fabric", item.get("fabric_name", ""))
    if not fabric_name:
        return 0
    obj, created = ProxmoxSdnFabric.objects.get_or_create(
        endpoint=endpoint,
        cluster_name=cluster_name,
        fabric_name=fabric_name,
        defaults={
            "fabric_type": item.get("type") or "",
            "asn": item.get("asn"),
            "advertise_subnets": bool(item.get("advertise_subnets", False)),
            "disable_arp_nd_suppression": bool(
                item.get("disable_arp_nd_suppression", False)
            ),
            "vrf_vxlan": item.get("vrf_vxlan"),
            "peers": item.get("peers", []),
            "status": FirewallSyncStatusChoices.ACTIVE,
            "raw_config": item,
        },
    )
    if created:
        result.fabrics_created += 1
    else:
        obj.fabric_type = item.get("type") or obj.fabric_type
        obj.asn = item.get("asn")
        obj.advertise_subnets = bool(item.get("advertise_subnets"))
        obj.disable_arp_nd_suppression = bool(item.get("disable_arp_nd_suppression"))
        obj.vrf_vxlan = item.get("vrf_vxlan")
        obj.peers = item.get("peers") if item.get("peers") is not None else obj.peers
        obj.status = FirewallSyncStatusChoices.ACTIVE
        obj.raw_config = item
        obj.save()
        result.fabrics_updated += 1
    return obj.pk


def _upsert_route_map(
    endpoint: ProxmoxEndpoint, item: dict, result: SdnSyncResult
) -> int:
    cluster_name = item.get("cluster_name", "")
    name = item.get("name", "")
    if not name:
        return 0
    order = item.get("order") or 0
    obj, created = ProxmoxSdnRouteMap.objects.get_or_create(
        endpoint=endpoint,
        cluster_name=cluster_name,
        name=name,
        order=order,
        defaults={
            "action": item.get("action", ""),
            "match_peer": item.get("match_peer", ""),
            "match_ip": item.get("match_ip", ""),
            "set_community": item.get("set_community", ""),
            "status": FirewallSyncStatusChoices.ACTIVE,
            "raw_config": item,
        },
    )
    if created:
        result.route_maps_created += 1
    else:
        obj.action = item.get("action", obj.action)
        obj.match_peer = item.get("match_peer", obj.match_peer)
        obj.match_ip = item.get("match_ip", obj.match_ip)
        obj.set_community = item.get("set_community", obj.set_community)
        obj.status = FirewallSyncStatusChoices.ACTIVE
        obj.raw_config = item
        obj.save()
        result.route_maps_updated += 1
    return obj.pk


def _upsert_prefix_list(
    endpoint: ProxmoxEndpoint, item: dict, result: SdnSyncResult
) -> int:
    cluster_name = item.get("cluster_name", "")
    name = item.get("name", "")
    if not name:
        return 0
    obj, created = ProxmoxSdnPrefixList.objects.get_or_create(
        endpoint=endpoint,
        cluster_name=cluster_name,
        name=name,
        cidr=item.get("cidr", ""),
        defaults={
            "action": item.get("action", ""),
            "le": item.get("le"),
            "ge": item.get("ge"),
            "status": FirewallSyncStatusChoices.ACTIVE,
            "raw_config": item,
        },
    )
    if created:
        result.prefix_lists_created += 1
    else:
        obj.cidr = item.get("cidr", obj.cidr)
        obj.action = item.get("action", obj.action)
        obj.le = item.get("le")
        obj.ge = item.get("ge")
        obj.status = FirewallSyncStatusChoices.ACTIVE
        obj.raw_config = item
        obj.save()
        result.prefix_lists_updated += 1
    return obj.pk


def _fetch_list(
    url: str, headers: dict, verify_ssl: bool, params: dict[str, str]
) -> list[dict] | None:
    try:
        resp = requests.get(
            url,
            params=params,
            headers=headers,
            verify=verify_ssl,
            timeout=SYNC_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, list) else None
    except requests.RequestException as exc:
        logger.error("HTTP error fetching %s: %s", url, exc)
        return None


def sync_sdn(
    fastapi_url: str | None = None,
    auth_headers: dict | None = None,
) -> SdnSyncResult:
    """Sync SDN fabrics, route maps, and prefix lists for all Proxmox endpoints."""
    result = SdnSyncResult()

    verify_ssl = True
    if not fastapi_url:
        ctx = get_fastapi_request_context()
        if ctx is None or not ctx.http_url:
            result.error = "FastAPI endpoint not configured or has no URL"
            logger.error(result.error)
            return result
        fastapi_url = ctx.http_url
        verify_ssl = bool(ctx.verify_ssl)
        if auth_headers is None:
            auth_headers = ctx.headers or {}

    if auth_headers is None:
        auth_headers = {}

    scope_params, _, scope_error = enabled_backend_endpoint_scope(
        base_url=fastapi_url,
        auth_headers=auth_headers,
        backend_verify_ssl=verify_ssl,
        timeout=SYNC_TIMEOUT,
    )
    if scope_error:
        result.error = scope_error
        logger.error(result.error)
        return result
    if scope_params is None:
        result.success = True
        logger.info("No enabled Proxmox endpoints configured; skipping SDN sync")
        return result

    fabrics = _fetch_list(
        f"{fastapi_url}/proxmox/sdn/fabrics",
        auth_headers,
        verify_ssl,
        scope_params,
    )
    route_maps = _fetch_list(
        f"{fastapi_url}/proxmox/sdn/route-maps",
        auth_headers,
        verify_ssl,
        scope_params,
    )
    prefix_lists = _fetch_list(
        f"{fastapi_url}/proxmox/sdn/prefix-lists",
        auth_headers,
        verify_ssl,
        scope_params,
    )

    if fabrics is None or route_maps is None or prefix_lists is None:
        result.error = "Failed to fetch one or more SDN endpoints from proxbox-api"
        logger.error(result.error)
        return result

    processed_fabric_endpoints: set[int] = set()
    processed_route_map_endpoints: set[int] = set()
    processed_prefix_list_endpoints: set[int] = set()
    synced_fabric_pks: set[int] = set()
    synced_route_map_pks: set[int] = set()
    synced_prefix_list_pks: set[int] = set()
    endpoint_runtime_seconds: dict[int, float] = {}
    endpoint_names: dict[int, str] = {}

    def record_endpoint_runtime(
        endpoint: ProxmoxEndpoint, runtime_seconds: float
    ) -> None:
        endpoint_names.setdefault(endpoint.pk, str(endpoint))
        endpoint_runtime_seconds[endpoint.pk] = (
            endpoint_runtime_seconds.get(endpoint.pk, 0.0) + runtime_seconds
        )

    with transaction.atomic():
        for item in fabrics:
            cluster_name = item.get("cluster_name", "")
            endpoint = (
                _resolve_endpoint_by_cluster_name(cluster_name)
                if cluster_name
                else None
            )
            if endpoint is None:
                logger.warning(
                    "Cannot resolve endpoint for cluster_name=%r, skipping SDN fabric",
                    cluster_name,
                )
                continue
            upsert_started = time.monotonic()
            pk = _upsert_fabric(endpoint, item, result)
            upsert_runtime = time.monotonic() - upsert_started
            if pk:
                record_endpoint_runtime(endpoint, upsert_runtime)
                synced_fabric_pks.add(pk)
                processed_fabric_endpoints.add(endpoint.pk)

        for item in route_maps:
            cluster_name = item.get("cluster_name", "")
            endpoint = (
                _resolve_endpoint_by_cluster_name(cluster_name)
                if cluster_name
                else None
            )
            if endpoint is None:
                continue
            upsert_started = time.monotonic()
            pk = _upsert_route_map(endpoint, item, result)
            upsert_runtime = time.monotonic() - upsert_started
            if pk:
                record_endpoint_runtime(endpoint, upsert_runtime)
                synced_route_map_pks.add(pk)
                processed_route_map_endpoints.add(endpoint.pk)

        for item in prefix_lists:
            cluster_name = item.get("cluster_name", "")
            endpoint = (
                _resolve_endpoint_by_cluster_name(cluster_name)
                if cluster_name
                else None
            )
            if endpoint is None:
                continue
            upsert_started = time.monotonic()
            pk = _upsert_prefix_list(endpoint, item, result)
            upsert_runtime = time.monotonic() - upsert_started
            if pk:
                record_endpoint_runtime(endpoint, upsert_runtime)
                synced_prefix_list_pks.add(pk)
                processed_prefix_list_endpoints.add(endpoint.pk)

        if processed_fabric_endpoints:
            stale_fabrics = (
                ProxmoxSdnFabric.objects.filter(
                    endpoint_id__in=processed_fabric_endpoints
                )
                .exclude(pk__in=synced_fabric_pks)
                .update(status=FirewallSyncStatusChoices.STALE)
            )
            result.fabrics_stale += stale_fabrics

        if processed_route_map_endpoints:
            stale_route_maps = (
                ProxmoxSdnRouteMap.objects.filter(
                    endpoint_id__in=processed_route_map_endpoints
                )
                .exclude(pk__in=synced_route_map_pks)
                .update(status=FirewallSyncStatusChoices.STALE)
            )
            result.route_maps_stale += stale_route_maps

        if processed_prefix_list_endpoints:
            stale_prefix_lists = (
                ProxmoxSdnPrefixList.objects.filter(
                    endpoint_id__in=processed_prefix_list_endpoints
                )
                .exclude(pk__in=synced_prefix_list_pks)
                .update(status=FirewallSyncStatusChoices.STALE)
            )
            result.prefix_lists_stale += stale_prefix_lists

    result.endpoints_processed = len(
        processed_fabric_endpoints
        | processed_route_map_endpoints
        | processed_prefix_list_endpoints
    )
    result.per_endpoint = [
        {
            "endpoint_id": endpoint_id,
            "endpoint_name": endpoint_names.get(endpoint_id, f"Endpoint {endpoint_id}"),
            "success": True,
            "runtime_seconds": round(runtime_seconds, 3),
        }
        for endpoint_id, runtime_seconds in endpoint_runtime_seconds.items()
    ]
    result.success = True
    logger.info(
        "SDN sync complete: %d endpoint(s) processed, "
        "fabrics=%d/%d, route_maps=%d/%d, prefix_lists=%d/%d",
        result.endpoints_processed,
        result.fabrics_created,
        result.fabrics_updated,
        result.route_maps_created,
        result.route_maps_updated,
        result.prefix_lists_created,
        result.prefix_lists_updated,
    )
    return result
