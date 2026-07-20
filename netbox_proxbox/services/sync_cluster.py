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

logger = logging.getLogger(__name__)


def _endpoint_sync_mode(endpoint: ProxmoxEndpoint, resource_type: str) -> str:
    try:
        return endpoint.effective_sync_mode(resource_type)
    except (AttributeError, ValueError):
        return SyncModeChoices.ALWAYS


def sync_cluster_and_nodes(
    endpoint_id: int,
    fastapi_url: str | None = None,
    auth_headers: dict | None = None,
) -> ClusterSyncResult:
    """
    Sync cluster and node data for a Proxmox endpoint from proxbox-api.

    Args:
        endpoint_id: ProxmoxEndpoint ID to sync.
        fastapi_url: Optional FastAPI base URL override (resolved from FastAPIEndpoint if omitted).
        auth_headers: Optional auth headers override for proxbox-api.

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
        ctx = get_fastapi_request_context()
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
        cluster_resp = requests.get(
            f"{fastapi_url}/proxmox/cluster/status",
            headers=auth_headers,
            params=scope_params,
            verify=verify_ssl,
            timeout=30,
        )
        cluster_resp.raise_for_status()
        cluster_data = ProxmoxClusterStatusResponse.model_validate(cluster_resp.json())

        if not cluster_data.records:
            logger.warning("No cluster data returned for endpoint %s", endpoint_id)
            result.error = "No cluster data returned from proxbox-api"
            return result

        node_detail_data: list[ProxmoxNodeDetail] = []
        node_detail_resp = requests.get(
            f"{fastapi_url}/proxmox/nodes/",
            headers=auth_headers,
            params=scope_params,
            verify=verify_ssl,
            timeout=30,
        )
        if node_detail_resp.ok:
            for record in iter_node_records(node_detail_resp.json()):
                node_detail_data.append(ProxmoxNodeDetail.model_validate(record))
        else:
            logger.warning(
                "Failed to fetch node details for endpoint %s: HTTP %s",
                endpoint_id,
                node_detail_resp.status_code,
            )

    except requests.RequestException as exc:
        error_msg = f"HTTP error syncing cluster/nodes: {exc}"
        logger.error(error_msg)
        result.error = error_msg
        return result

    # ------------------------------------------------------------------
    # DB phase — single atomic transaction for all writes.
    # ------------------------------------------------------------------
    try:
        with transaction.atomic():
            # Track existing node names to detect deletions.
            existing_node_names = set(
                ProxmoxNode.objects.filter(endpoint=endpoint).values_list(
                    "name", flat=True
                )
            )
            synced_node_names: set[str] = set()

            cluster_record = cluster_data.cluster_record
            node_records = cluster_data.node_records

            mode = derive_proxmox_endpoint_mode(cluster_record, node_records)

            if cluster_mode != SyncModeChoices.DISABLED and endpoint.mode != mode:
                endpoint.mode = mode
                endpoint.save(update_fields=["mode"])
                result.mode_updated = True
                logger.info("Updated endpoint %s mode to %s", endpoint_id, mode)

            # Sync cluster record when present.
            proxmox_cluster = None
            if cluster_record and cluster_mode != SyncModeChoices.DISABLED:
                cluster_name = cluster_record.name or endpoint.name
                cluster_defaults = {
                    "cluster_id": cluster_record.id or "",
                    "mode": mode,
                    "nodes_count": cluster_record.nodes or len(node_records),
                    "quorate": bool(cluster_record.quorate or 0),
                    "version": cluster_record.version,
                }
                proxmox_cluster = ProxmoxCluster.objects.filter(
                    endpoint=endpoint,
                    name=cluster_name,
                ).first()
                if proxmox_cluster and _bootstrap_only_should_skip_existing(
                    proxmox_cluster,
                    cluster_mode,
                ):
                    logger.info(
                        "Skipped bootstrap-only cluster %s for endpoint %s",
                        cluster_name,
                        endpoint_id,
                    )
                else:
                    proxmox_cluster, created = ProxmoxCluster.objects.update_or_create(
                        endpoint=endpoint,
                        name=cluster_name,
                        defaults=cluster_defaults,
                    )
                    if created and cluster_mode == SyncModeChoices.BOOTSTRAP_ONLY:
                        _add_bootstrap_only_tag(proxmox_cluster)
                    if created:
                        result.clusters_created += 1
                        log_action = "Created"
                    else:
                        result.clusters_updated += 1
                        log_action = "Updated"
                    logger.info(
                        "%s cluster %s for endpoint %s",
                        log_action,
                        cluster_name,
                        endpoint_id,
                    )
            elif cluster_record and cluster_mode == SyncModeChoices.DISABLED:
                proxmox_cluster = ProxmoxCluster.objects.filter(
                    endpoint=endpoint,
                    name=cluster_record.name or endpoint.name,
                ).first()

            # Build a lookup of detailed node metrics from the pre-fetched response.
            node_details_by_name: dict[str, ProxmoxNodeDetail] = {
                detail.node: detail for detail in node_detail_data if detail.node
            }

            # Sync each node record.
            for node_record in node_records:
                if node_mode == SyncModeChoices.DISABLED:
                    continue
                node_name = node_record.name or node_record.id or node_record.node
                if not node_name:
                    continue

                synced_node_names.add(node_name)

                node_defaults: dict[str, object] = {
                    "proxmox_cluster": proxmox_cluster,
                    "node_id": node_record.nodeid,
                    "ip_address": node_record.ip or None,
                    "online": bool(node_record.online or 0),
                    "local": bool(node_record.local or 0),
                }

                detail = node_details_by_name.get(node_name)
                if detail:
                    node_defaults.update(
                        {
                            "cpu_usage": detail.cpu,
                            "max_cpu": detail.maxcpu,
                            "memory_usage": detail.mem,
                            "max_memory": detail.maxmem,
                            "ssl_fingerprint": detail.ssl_fingerprint or "",
                            "support_level": detail.level or "",
                            "location": detail.location or "",
                        }
                    )

                node = ProxmoxNode.objects.filter(
                    endpoint=endpoint,
                    name=node_name,
                ).first()
                if node and _bootstrap_only_should_skip_existing(node, node_mode):
                    logger.info(
                        "Skipped bootstrap-only node %s for endpoint %s",
                        node_name,
                        endpoint_id,
                    )
                else:
                    node, created = ProxmoxNode.objects.update_or_create(
                        endpoint=endpoint,
                        name=node_name,
                        defaults=node_defaults,
                    )
                    if created and node_mode == SyncModeChoices.BOOTSTRAP_ONLY:
                        _add_bootstrap_only_tag(node)
                    if created:
                        result.nodes_created += 1
                        log_action = "Created"
                    else:
                        result.nodes_updated += 1
                        log_action = "Updated"
                    logger.info(
                        "%s node %s for endpoint %s",
                        log_action,
                        node_name,
                        endpoint_id,
                    )

            # Delete nodes that no longer exist in Proxmox.
            stale_names = existing_node_names - synced_node_names
            if stale_names and node_mode != SyncModeChoices.DISABLED:
                stale_qs = ProxmoxNode.objects.filter(
                    endpoint=endpoint, name__in=stale_names
                )
                if node_mode == SyncModeChoices.BOOTSTRAP_ONLY:
                    stale_ids = [
                        node.pk
                        for node in stale_qs
                        if not _has_bootstrap_only_tag(node)
                    ]
                    stale_qs = stale_qs.filter(pk__in=stale_ids)
                deleted_count, _ = stale_qs.delete()
                result.nodes_deleted = deleted_count
                logger.info(
                    "Deleted %s stale nodes for endpoint %s", deleted_count, endpoint_id
                )

        result.success = True
        logger.info("Successfully synced cluster/nodes for endpoint %s", endpoint_id)

    except Exception as exc:
        error_msg = f"Error syncing cluster/nodes: {exc}"
        logger.exception(error_msg)
        result.error = error_msg

    return result
