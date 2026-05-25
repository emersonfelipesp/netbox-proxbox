"""Sync service for Proxmox datacenter-level objects from proxbox-api.

Calls:
  - GET /proxmox/datacenter/cpu-models

Results are upserted into the ProxmoxDatacenterCpuModel Django model.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

import requests
from django.db import transaction

from netbox_proxbox.choices import FirewallSyncStatusChoices
from netbox_proxbox.models import ProxmoxDatacenterCpuModel, ProxmoxEndpoint
from netbox_proxbox.services.backend_proxy import get_fastapi_request_context

logger = logging.getLogger(__name__)

SYNC_TIMEOUT = 30


@dataclass
class DatacenterSyncResult:
    success: bool = False
    error: str | None = None
    endpoints_processed: int = 0
    cpu_models_created: int = 0
    cpu_models_updated: int = 0
    cpu_models_stale: int = 0
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
    except Exception as exc:
        logger.warning("DB error resolving cluster %r: %s", cluster_name, exc)
    return ProxmoxEndpoint.objects.filter(name=cluster_name).first()


def _upsert_cpu_model(
    endpoint: ProxmoxEndpoint, item: dict, result: DatacenterSyncResult
) -> int:
    cluster_name = item.get("cluster_name", "")
    cputype = item.get("cputype", item.get("name", ""))
    if not cputype:
        return 0
    obj, created = ProxmoxDatacenterCpuModel.objects.get_or_create(
        endpoint=endpoint,
        cluster_name=cluster_name,
        cputype=cputype,
        defaults={
            "base_cputype": item.get("base_cputype", ""),
            "flags": item.get("flags", ""),
            "vendor_id": item.get("vendor-id", item.get("vendor_id", "")),
            "level": item.get("level"),
            "description": item.get("description", ""),
            "status": FirewallSyncStatusChoices.ACTIVE,
            "raw_config": item,
        },
    )
    if created:
        result.cpu_models_created += 1
    else:
        obj.base_cputype = item.get("base_cputype") or ""
        obj.flags = item.get("flags") or ""
        obj.vendor_id = item.get("vendor-id", item.get("vendor_id")) or ""
        obj.level = item.get("level")
        obj.description = item.get("description") or ""
        obj.status = FirewallSyncStatusChoices.ACTIVE
        obj.raw_config = item
        obj.save()
        result.cpu_models_updated += 1
    return obj.pk


def sync_datacenter(
    fastapi_url: str | None = None,
    auth_headers: dict | None = None,
) -> DatacenterSyncResult:
    """Sync datacenter CPU models for all Proxmox endpoints."""
    result = DatacenterSyncResult()

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

    try:
        resp = requests.get(
            f"{fastapi_url}/proxmox/datacenter/cpu-models",
            headers=auth_headers,
            verify=verify_ssl,
            timeout=SYNC_TIMEOUT,
        )
        resp.raise_for_status()
        cpu_models_list = resp.json()
    except requests.RequestException as exc:
        result.error = f"HTTP error fetching datacenter CPU models: {exc}"
        logger.error(result.error)
        return result

    if not isinstance(cpu_models_list, list):
        result.error = f"Unexpected response type: {type(cpu_models_list).__name__}"
        logger.error(result.error)
        return result

    processed_endpoints: set[int] = set()
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
        synced_pks: list[int] = []
        for item in cpu_models_list:
            cluster_name = item.get("cluster_name", "")
            endpoint = (
                _resolve_endpoint_by_cluster_name(cluster_name)
                if cluster_name
                else None
            )
            if endpoint is None:
                logger.warning(
                    "Cannot resolve endpoint for cluster_name=%r, skipping CPU model",
                    cluster_name,
                )
                continue
            upsert_started = time.monotonic()
            pk = _upsert_cpu_model(endpoint, item, result)
            upsert_runtime = time.monotonic() - upsert_started
            if pk:
                synced_pks.append(pk)
                record_endpoint_runtime(endpoint, upsert_runtime)
                processed_endpoints.add(endpoint.pk)

        stale = (
            ProxmoxDatacenterCpuModel.objects.filter(
                endpoint_id__in=processed_endpoints
            )
            .exclude(pk__in=synced_pks)
            .update(status=FirewallSyncStatusChoices.STALE)
        )
        result.cpu_models_stale += stale

    result.endpoints_processed = len(processed_endpoints)
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
        "Datacenter sync complete: %d endpoint(s) processed, cpu_models=%d/%d/%d (created/updated/stale)",
        result.endpoints_processed,
        result.cpu_models_created,
        result.cpu_models_updated,
        result.cpu_models_stale,
    )
    return result
