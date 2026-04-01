"""Sync service for Proxmox cluster and node data from proxbox-api."""

from __future__ import annotations

import logging
from typing import Any

import requests

from django.db import transaction

from netbox_proxbox.models import ProxmoxCluster, ProxmoxEndpoint, ProxmoxNode
from netbox_proxbox.services.backend_proxy import get_fastapi_request_context

logger = logging.getLogger(__name__)


def sync_cluster_and_nodes(
    endpoint_id: int,
    fastapi_url: str | None = None,
    auth_headers: dict | None = None,
) -> dict[str, Any]:
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
        return {"success": False, "error": "Endpoint not found"}

    # Resolve FastAPI connection parameters from the configured endpoint when not supplied.
    verify_ssl = True
    if not fastapi_url:
        ctx = get_fastapi_request_context()
        if ctx is None or not ctx.get("http_url"):
            logger.error("FastAPI endpoint not configured or has no URL")
            return {"success": False, "error": "FastAPI URL not configured"}
        fastapi_url = ctx["http_url"]
        verify_ssl = ctx.get("verify_ssl", True)
        if auth_headers is None:
            auth_headers = ctx.get("headers") or {}

    if auth_headers is None:
        auth_headers = {}

    result: dict[str, Any] = {
        "success": False,
        "endpoint_id": endpoint_id,
        "endpoint_name": str(endpoint),
        "clusters_created": 0,
        "clusters_updated": 0,
        "nodes_created": 0,
        "nodes_updated": 0,
        "nodes_deleted": 0,
        "mode_updated": False,
        "error": None,
    }

    # ------------------------------------------------------------------
    # HTTP phase — fetch all data before opening any DB transaction.
    # ------------------------------------------------------------------
    try:
        cluster_resp = requests.get(
            f"{fastapi_url}/proxmox/cluster/status",
            headers=auth_headers,
            verify=verify_ssl,
            timeout=30,
        )
        cluster_resp.raise_for_status()
        cluster_data: dict = cluster_resp.json()

        if not cluster_data:
            logger.warning("No cluster data returned for endpoint %s", endpoint_id)
            result["error"] = "No cluster data returned from proxbox-api"
            return result

        node_detail_data: dict = {}
        node_detail_resp = requests.get(
            f"{fastapi_url}/proxmox/nodes/",
            headers=auth_headers,
            verify=verify_ssl,
            timeout=30,
        )
        if node_detail_resp.ok:
            node_detail_data = node_detail_resp.json()
        else:
            logger.warning(
                "Failed to fetch node details for endpoint %s: HTTP %s",
                endpoint_id,
                node_detail_resp.status_code,
            )

    except requests.RequestException as exc:
        error_msg = f"HTTP error syncing cluster/nodes: {exc}"
        logger.error(error_msg)
        result["error"] = error_msg
        return result

    # ------------------------------------------------------------------
    # DB phase — single atomic transaction for all writes.
    # ------------------------------------------------------------------
    try:
        with transaction.atomic():
            # Track existing node names to detect deletions.
            existing_node_names = set(
                ProxmoxNode.objects.filter(endpoint=endpoint).values_list("name", flat=True)
            )
            synced_node_names: set[str] = set()

            for session_name, session_data in cluster_data.items():
                if not isinstance(session_data, list):
                    continue

                cluster_record = None
                node_records = []

                for item in session_data:
                    if item.get("type") == "cluster":
                        cluster_record = item
                    elif item.get("type") == "node":
                        node_records.append(item)

                # Determine mode from topology.
                if cluster_record and len(node_records) > 1:
                    mode = "cluster"
                elif len(node_records) == 1:
                    mode = "standalone"
                else:
                    mode = "undefined"

                if endpoint.mode != mode:
                    endpoint.mode = mode
                    endpoint.save(update_fields=["mode"])
                    result["mode_updated"] = True
                    logger.info("Updated endpoint %s mode to %s", endpoint_id, mode)

                # Sync cluster record when present.
                proxmox_cluster = None
                if cluster_record:
                    cluster_name = cluster_record.get("name", session_name)
                    cluster_defaults = {
                        "cluster_id": cluster_record.get("id", ""),
                        "mode": mode,
                        "nodes_count": cluster_record.get("nodes", len(node_records)),
                        "quorate": bool(cluster_record.get("quorate", 0)),
                        "version": cluster_record.get("version"),
                    }
                    proxmox_cluster, created = ProxmoxCluster.objects.update_or_create(
                        endpoint=endpoint,
                        name=cluster_name,
                        defaults=cluster_defaults,
                    )
                    if created:
                        result["clusters_created"] += 1
                        logger.info("Created cluster %s for endpoint %s", cluster_name, endpoint_id)
                    else:
                        result["clusters_updated"] += 1
                        logger.info("Updated cluster %s for endpoint %s", cluster_name, endpoint_id)

                # Build a lookup of detailed node metrics from the pre-fetched response.
                node_details_by_name: dict[str, dict] = {}
                for session_nodes in node_detail_data.values():
                    if isinstance(session_nodes, list):
                        for detail in session_nodes:
                            node_name = detail.get("node")
                            if node_name:
                                node_details_by_name[node_name] = detail

                # Sync each node record.
                for node_record in node_records:
                    node_name = node_record.get("name") or node_record.get("node")
                    if not node_name:
                        continue

                    synced_node_names.add(node_name)

                    node_defaults: dict[str, Any] = {
                        "proxmox_cluster": proxmox_cluster,
                        "node_id": node_record.get("nodeid"),
                        "ip_address": node_record.get("ip") or None,
                        "online": bool(node_record.get("online", 0)),
                        "local": bool(node_record.get("local", 0)),
                    }

                    detail = node_details_by_name.get(node_name, {})
                    if detail:
                        node_defaults.update(
                            {
                                "cpu_usage": detail.get("cpu"),
                                "max_cpu": detail.get("maxcpu"),
                                "memory_usage": detail.get("mem"),
                                "max_memory": detail.get("maxmem"),
                                "ssl_fingerprint": detail.get("ssl_fingerprint", ""),
                                "support_level": detail.get("level", ""),
                            }
                        )

                    node, created = ProxmoxNode.objects.update_or_create(
                        endpoint=endpoint,
                        name=node_name,
                        defaults=node_defaults,
                    )
                    if created:
                        result["nodes_created"] += 1
                        logger.info("Created node %s for endpoint %s", node_name, endpoint_id)
                    else:
                        result["nodes_updated"] += 1

            # Delete nodes that no longer exist in Proxmox.
            stale_names = existing_node_names - synced_node_names
            if stale_names:
                deleted_count, _ = ProxmoxNode.objects.filter(
                    endpoint=endpoint, name__in=stale_names
                ).delete()
                result["nodes_deleted"] = deleted_count
                logger.info("Deleted %s stale nodes for endpoint %s", deleted_count, endpoint_id)

        result["success"] = True
        logger.info("Successfully synced cluster/nodes for endpoint %s", endpoint_id)

    except Exception as exc:
        error_msg = f"Error syncing cluster/nodes: {exc}"
        logger.exception(error_msg)
        result["error"] = error_msg

    return result
