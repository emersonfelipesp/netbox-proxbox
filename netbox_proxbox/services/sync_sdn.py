"""Sync service for Proxmox SDN objects from proxbox-api.

Calls the SDN endpoints on proxbox-api:
  - GET /proxmox/sdn/fabrics
  - GET /proxmox/sdn/route-maps
  - GET /proxmox/sdn/prefix-lists

Results are upserted into the three SDN Django models.
"""

from __future__ import annotations

import logging
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
        if cluster and cluster.endpoint_id:
            return cluster.endpoint
    except Exception:
        pass
    return ProxmoxEndpoint.objects.filter(name=cluster_name).first()


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
            "fabric_type": item.get("type", ""),
            "asn": item.get("asn"),
            "advertise_subnets": bool(item.get("advertise_subnets", False)),
            "disable_arp_nd_suppression": bool(item.get("disable_arp_nd_suppression", False)),
            "vrf_vxlan": item.get("vrf_vxlan"),
            "peers": item.get("peers", []),
            "status": FirewallSyncStatusChoices.ACTIVE,
            "raw_config": item,
        },
    )
    if created:
        result.fabrics_created += 1
    else:
        obj.fabric_type = item.get("type", obj.fabric_type)
        obj.asn = item.get("asn", obj.asn)
        obj.advertise_subnets = bool(item.get("advertise_subnets", obj.advertise_subnets))
        obj.disable_arp_nd_suppression = bool(item.get("disable_arp_nd_suppression", obj.disable_arp_nd_suppression))
        obj.vrf_vxlan = item.get("vrf_vxlan", obj.vrf_vxlan)
        obj.peers = item.get("peers", obj.peers)
        obj.status = FirewallSyncStatusChoices.ACTIVE
        obj.raw_config = item
        obj.save()
        result.fabrics_updated += 1
    return obj.pk


def _upsert_route_map(endpoint: ProxmoxEndpoint, item: dict, result: SdnSyncResult) -> int:
    cluster_name = item.get("cluster_name", "")
    name = item.get("name", "")
    if not name:
        return 0
    obj, created = ProxmoxSdnRouteMap.objects.get_or_create(
        endpoint=endpoint,
        cluster_name=cluster_name,
        name=name,
        defaults={
            "action": item.get("action", ""),
            "match_peer": item.get("match_peer", ""),
            "match_ip": item.get("match_ip", ""),
            "set_community": item.get("set_community", ""),
            "order": item.get("order", 0),
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
        obj.order = item.get("order", obj.order)
        obj.status = FirewallSyncStatusChoices.ACTIVE
        obj.raw_config = item
        obj.save()
        result.route_maps_updated += 1
    return obj.pk


def _upsert_prefix_list(endpoint: ProxmoxEndpoint, item: dict, result: SdnSyncResult) -> int:
    cluster_name = item.get("cluster_name", "")
    name = item.get("name", "")
    if not name:
        return 0
    obj, created = ProxmoxSdnPrefixList.objects.get_or_create(
        endpoint=endpoint,
        cluster_name=cluster_name,
        name=name,
        defaults={
            "cidr": item.get("cidr", ""),
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
        obj.le = item.get("le", obj.le)
        obj.ge = item.get("ge", obj.ge)
        obj.status = FirewallSyncStatusChoices.ACTIVE
        obj.raw_config = item
        obj.save()
        result.prefix_lists_updated += 1
    return obj.pk


def _fetch_list(url: str, headers: dict, verify_ssl: bool) -> list[dict] | None:
    try:
        resp = requests.get(url, headers=headers, verify=verify_ssl, timeout=SYNC_TIMEOUT)
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

    fabrics = _fetch_list(f"{fastapi_url}/proxmox/sdn/fabrics", auth_headers, verify_ssl) or []
    route_maps = _fetch_list(f"{fastapi_url}/proxmox/sdn/route-maps", auth_headers, verify_ssl) or []
    prefix_lists = _fetch_list(f"{fastapi_url}/proxmox/sdn/prefix-lists", auth_headers, verify_ssl) or []

    processed_endpoints: set[int] = set()

    with transaction.atomic():
        for item in fabrics:
            cluster_name = item.get("cluster_name", "")
            endpoint = _resolve_endpoint_by_cluster_name(cluster_name) if cluster_name else None
            if endpoint is None:
                logger.warning("Cannot resolve endpoint for cluster_name=%r, skipping SDN fabric", cluster_name)
                continue
            _upsert_fabric(endpoint, item, result)
            processed_endpoints.add(endpoint.pk)

        for item in route_maps:
            cluster_name = item.get("cluster_name", "")
            endpoint = _resolve_endpoint_by_cluster_name(cluster_name) if cluster_name else None
            if endpoint is None:
                continue
            _upsert_route_map(endpoint, item, result)
            processed_endpoints.add(endpoint.pk)

        for item in prefix_lists:
            cluster_name = item.get("cluster_name", "")
            endpoint = _resolve_endpoint_by_cluster_name(cluster_name) if cluster_name else None
            if endpoint is None:
                continue
            _upsert_prefix_list(endpoint, item, result)
            processed_endpoints.add(endpoint.pk)

    result.endpoints_processed = len(processed_endpoints)
    result.success = True
    logger.info(
        "SDN sync complete: %d endpoint(s) processed, "
        "fabrics=%d/%d, route_maps=%d/%d, prefix_lists=%d/%d",
        result.endpoints_processed,
        result.fabrics_created, result.fabrics_updated,
        result.route_maps_created, result.route_maps_updated,
        result.prefix_lists_created, result.prefix_lists_updated,
    )
    return result
