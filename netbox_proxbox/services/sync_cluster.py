"""Sync service for Proxmox cluster and node data from proxbox-api."""

# Result payload shape still exposes the legacy "success" and "error" keys via
# ClusterSyncResult so older callers and contract tests keep working.

from __future__ import annotations

import logging

import requests

from django.db import transaction

try:
    from netbox_proxbox.choices import SyncModeChoices
except ImportError:  # pragma: no cover - compatibility for focused import stubs

    class SyncModeChoices:  # type: ignore[no-redef]
        ALWAYS = "always"
        BOOTSTRAP_ONLY = "bootstrap_only"
        DISABLED = "disabled"


from netbox_proxbox.models import ProxmoxCluster, ProxmoxEndpoint, ProxmoxNode
from netbox_proxbox.schemas import (
    ClusterSyncResult,
    ProxmoxClusterStatusResponse,
    ProxmoxNodeDetail,
)
from netbox_proxbox.schemas._formatters import iter_node_records, iter_scalar_records
from netbox_proxbox.services.backend_proxy import get_fastapi_request_context
from netbox_proxbox.services.proxmox_mode import derive_proxmox_endpoint_mode
from netbox_proxbox.sync_stages import (
    _add_bootstrap_only_tag,
    _bootstrap_only_should_skip_existing,
    _has_bootstrap_only_tag,
)
from netbox_proxbox.views.backend_sync import resolve_backend_endpoint_id
from netbox_proxbox.services.sync_deadline import remaining_timeout

logger = logging.getLogger(__name__)


def _endpoint_sync_mode(endpoint: ProxmoxEndpoint, resource_type: str) -> str:
    try:
        return endpoint.effective_sync_mode(resource_type)
    except (AttributeError, ValueError):
        return SyncModeChoices.ALWAYS


def _fetch_cluster_and_node_data(
    fastapi_url: str,
    auth_headers: dict,
    verify_ssl: bool,
    scope_params: dict[str, str],
    endpoint_id: int,
    deadline: float | None,
) -> tuple[ProxmoxClusterStatusResponse, list[ProxmoxNodeDetail]]:
    """Fetch the endpoint-scoped cluster status and optional node details."""
    cluster_resp = requests.get(
        f"{fastapi_url}/proxmox/cluster/status",
        headers=auth_headers,
        params=scope_params,
        verify=verify_ssl,
        timeout=remaining_timeout(deadline, 30.0),
        allow_redirects=False,
    )
    cluster_resp.raise_for_status()
    cluster_data = ProxmoxClusterStatusResponse.model_validate(cluster_resp.json())
    node_detail_resp = requests.get(
        f"{fastapi_url}/proxmox/nodes/",
        headers=auth_headers,
        params=scope_params,
        verify=verify_ssl,
        timeout=remaining_timeout(deadline, 30.0),
        allow_redirects=False,
    )
    if not node_detail_resp.ok:
        logger.warning(
            "Failed to fetch node details for endpoint %s: HTTP %s",
            endpoint_id,
            node_detail_resp.status_code,
        )
        return cluster_data, []
    node_details = [
        ProxmoxNodeDetail.model_validate(record)
        for record in iter_node_records(node_detail_resp.json())
    ]
    return cluster_data, node_details


def _sync_cluster_record(
    endpoint: ProxmoxEndpoint,
    endpoint_id: int,
    cluster_record: object,
    node_records: list,
    cluster_mode: str,
    mode: str,
    result: ClusterSyncResult,
) -> ProxmoxCluster | None:
    """Upsert or resolve the cluster row for the node phase."""
    if not cluster_record:
        return None
    cluster_name = cluster_record.name or endpoint.name
    existing = ProxmoxCluster.objects.filter(
        endpoint=endpoint, name=cluster_name
    ).first()
    if cluster_mode == SyncModeChoices.DISABLED:
        return existing
    if existing and _bootstrap_only_should_skip_existing(existing, cluster_mode):
        logger.info(
            "Skipped bootstrap-only cluster %s for endpoint %s",
            cluster_name,
            endpoint_id,
        )
        return existing
    cluster, created = ProxmoxCluster.objects.update_or_create(
        endpoint=endpoint,
        name=cluster_name,
        defaults={
            "cluster_id": cluster_record.id or "",
            "mode": mode,
            "nodes_count": cluster_record.nodes or len(node_records),
            "quorate": bool(cluster_record.quorate or 0),
            "version": cluster_record.version,
        },
    )
    if created and cluster_mode == SyncModeChoices.BOOTSTRAP_ONLY:
        _add_bootstrap_only_tag(cluster)
    if created:
        result.clusters_created += 1
    else:
        result.clusters_updated += 1
    logger.info(
        "%s cluster %s for endpoint %s",
        "Created" if created else "Updated",
        cluster_name,
        endpoint_id,
    )
    return cluster


def _sync_node_records(
    endpoint: ProxmoxEndpoint,
    endpoint_id: int,
    proxmox_cluster: ProxmoxCluster | None,
    node_records: list,
    node_detail_data: list[ProxmoxNodeDetail],
    node_mode: str,
    result: ClusterSyncResult,
) -> set[str]:
    """Upsert the endpoint's node records and return their live names."""
    if node_mode == SyncModeChoices.DISABLED:
        return set()
    details_by_name = {
        detail.node: detail for detail in node_detail_data if detail.node
    }
    synced_names: set[str] = set()
    for node_record in node_records:
        node_name = node_record.name or node_record.id or node_record.node
        if not node_name:
            continue
        synced_names.add(node_name)
        defaults: dict[str, object] = {
            "proxmox_cluster": proxmox_cluster,
            "node_id": node_record.nodeid,
            "ip_address": node_record.ip or None,
            "online": bool(node_record.online or 0),
            "local": bool(node_record.local or 0),
        }
        detail = details_by_name.get(node_name)
        if detail:
            defaults.update(
                cpu_usage=detail.cpu,
                max_cpu=detail.maxcpu,
                memory_usage=detail.mem,
                max_memory=detail.maxmem,
                ssl_fingerprint=detail.ssl_fingerprint or "",
                support_level=detail.level or "",
                location=detail.location or "",
            )
        existing = ProxmoxNode.objects.filter(endpoint=endpoint, name=node_name).first()
        if existing and _bootstrap_only_should_skip_existing(existing, node_mode):
            logger.info(
                "Skipped bootstrap-only node %s for endpoint %s",
                node_name,
                endpoint_id,
            )
            continue
        node, created = ProxmoxNode.objects.update_or_create(
            endpoint=endpoint, name=node_name, defaults=defaults
        )
        if created and node_mode == SyncModeChoices.BOOTSTRAP_ONLY:
            _add_bootstrap_only_tag(node)
        if created:
            result.nodes_created += 1
        else:
            result.nodes_updated += 1
        logger.info(
            "%s node %s for endpoint %s",
            "Created" if created else "Updated",
            node_name,
            endpoint_id,
        )
    return synced_names


def _delete_stale_nodes(
    endpoint: ProxmoxEndpoint,
    endpoint_id: int,
    stale_names: set[str],
    node_mode: str,
    result: ClusterSyncResult,
) -> None:
    """Delete stale non-bootstrap rows when node synchronization permits it."""
    if not stale_names or node_mode == SyncModeChoices.DISABLED:
        return
    stale_qs = ProxmoxNode.objects.filter(endpoint=endpoint, name__in=stale_names)
    if node_mode == SyncModeChoices.BOOTSTRAP_ONLY:
        stale_ids = [node.pk for node in stale_qs if not _has_bootstrap_only_tag(node)]
        stale_qs = stale_qs.filter(pk__in=stale_ids)
    result.nodes_deleted, _ = stale_qs.delete()
    logger.info(
        "Deleted %s stale nodes for endpoint %s", result.nodes_deleted, endpoint_id
    )


def _persist_cluster_and_nodes(
    endpoint: ProxmoxEndpoint,
    endpoint_id: int,
    cluster_data: ProxmoxClusterStatusResponse,
    node_detail_data: list[ProxmoxNodeDetail],
    cluster_mode: str,
    node_mode: str,
    result: ClusterSyncResult,
) -> None:
    """Persist one endpoint's prefetched cluster and node inventory atomically."""
    with transaction.atomic():
        existing_names = set(
            ProxmoxNode.objects.filter(endpoint=endpoint).values_list("name", flat=True)
        )
        cluster_record = cluster_data.cluster_record
        node_records = cluster_data.node_records
        mode = derive_proxmox_endpoint_mode(cluster_record, node_records)
        if cluster_mode != SyncModeChoices.DISABLED and endpoint.mode != mode:
            endpoint.mode = mode
            endpoint.save(update_fields=["mode"])
            result.mode_updated = True
            logger.info("Updated endpoint %s mode to %s", endpoint_id, mode)
        cluster = _sync_cluster_record(
            endpoint,
            endpoint_id,
            cluster_record,
            node_records,
            cluster_mode,
            mode,
            result,
        )
        synced_names = _sync_node_records(
            endpoint,
            endpoint_id,
            cluster,
            node_records,
            node_detail_data,
            node_mode,
            result,
        )
        _delete_stale_nodes(
            endpoint,
            endpoint_id,
            existing_names - synced_names,
            node_mode,
            result,
        )


def sync_cluster_and_nodes(
    endpoint_id: int,
    fastapi_url: str | None = None,
    auth_headers: dict | None = None,
    fastapi_endpoint_id: int | None = None,
    deadline: float | None = None,
) -> ClusterSyncResult:
    """
    Sync cluster and node data for a Proxmox endpoint from proxbox-api.

    Args:
        endpoint_id: ProxmoxEndpoint ID to sync.
        fastapi_url: Optional FastAPI base URL override (resolved from FastAPIEndpoint if omitted).
        auth_headers: Optional auth headers override for proxbox-api.
        fastapi_endpoint_id: Optional `FastAPIEndpoint` pk pinning which backend
            row is resolved.  Only consulted when ``fastapi_url`` is omitted; it
            stops a multi-backend install from certifying one backend in the job
            preflight and then syncing against another.

    Returns:
        dict with sync status and counts.
    """
    try:
        endpoint = ProxmoxEndpoint.objects.get(pk=endpoint_id)
    except ProxmoxEndpoint.DoesNotExist:
        logger.error("ProxmoxEndpoint %s not found", endpoint_id)
        return ClusterSyncResult(error="Endpoint not found")

    if not bool(getattr(endpoint, "enabled", True)):
        logger.info("Skipping cluster/node sync for disabled endpoint %s", endpoint_id)
        return ClusterSyncResult(
            endpoint_id=endpoint_id,
            endpoint_name=str(endpoint),
            success=True,
            error=None,
        )

    # Resolve FastAPI connection parameters from the configured endpoint when not supplied.
    verify_ssl = True
    if not fastapi_url:
        ctx = get_fastapi_request_context(endpoint_id=fastapi_endpoint_id)
        if ctx is None or not ctx.http_url:
            logger.error("FastAPI endpoint not configured or has no URL")
            return ClusterSyncResult(error="FastAPI URL not configured")
        fastapi_url = ctx.http_url
        verify_ssl = bool(ctx.verify_ssl)
        if auth_headers is None:
            auth_headers = ctx.headers or {}

    if auth_headers is None:
        auth_headers = {}

    result = ClusterSyncResult(
        endpoint_id=endpoint_id,
        endpoint_name=str(endpoint),
    )
    cluster_mode = _endpoint_sync_mode(endpoint, "cluster")
    node_mode = _endpoint_sync_mode(endpoint, "node")
    if (
        cluster_mode == SyncModeChoices.DISABLED
        and node_mode == SyncModeChoices.DISABLED
    ):
        result.success = True
        logger.info(
            "Skipping cluster/node sync for endpoint %s: cluster and node sync modes are disabled",
            endpoint_id,
        )
        return result

    # ------------------------------------------------------------------
    # Endpoint identity — translate this plugin endpoint to the backend's
    # own database id so the status/node reads return ONLY this endpoint's
    # records. Without this scope the backend returns one record per enabled
    # endpoint and the plugin would attribute foreign clusters/nodes to this
    # endpoint. Fail loud rather than syncing the wrong endpoint.
    # ------------------------------------------------------------------
    backend_endpoint_id, resolve_error = resolve_backend_endpoint_id(
        endpoint,
        base_url=fastapi_url,
        auth_headers=auth_headers,
        backend_verify_ssl=verify_ssl,
        timeout=remaining_timeout(deadline, 30.0),
    )
    if backend_endpoint_id is None:
        logger.error(
            "Could not resolve backend endpoint id for endpoint %s: %s",
            endpoint_id,
            resolve_error,
        )
        result.error = resolve_error or "Could not resolve backend Proxmox endpoint id"
        return result

    scope_params = {"proxmox_endpoint_ids": str(backend_endpoint_id)}

    # ------------------------------------------------------------------
    # HTTP phase — fetch all data before opening any DB transaction.
    # ------------------------------------------------------------------
    try:
        cluster_data, node_detail_data = _fetch_cluster_and_node_data(
            fastapi_url,
            auth_headers,
            verify_ssl,
            scope_params,
            endpoint_id,
            deadline,
        )

        if not cluster_data.records:
            logger.warning("No cluster data returned for endpoint %s", endpoint_id)
            result.error = "No cluster data returned from proxbox-api"
            return result

    except requests.RequestException as exc:
        error_msg = f"HTTP error syncing cluster/nodes: {exc}"
        logger.error(error_msg)
        result.error = error_msg
        return result

    # ------------------------------------------------------------------
    # DB phase — single atomic transaction for all writes.
    # ------------------------------------------------------------------
    try:
        _persist_cluster_and_nodes(
            endpoint,
            endpoint_id,
            cluster_data,
            node_detail_data,
            cluster_mode,
            node_mode,
            result,
        )

        result.success = True
        logger.info("Successfully synced cluster/nodes for endpoint %s", endpoint_id)

    except Exception as exc:
        error_msg = f"Error syncing cluster/nodes: {exc}"
        logger.exception(error_msg)
        result.error = error_msg

    return result
