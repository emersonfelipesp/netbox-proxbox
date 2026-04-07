"""Data-building helpers extracted from the dashboard view."""

from __future__ import annotations

from virtualization.models import Cluster

from netbox_proxbox.models import ProxmoxEndpoint, ProxmoxNode
from netbox_proxbox.schemas import (
    ProxmoxClusterStatusResponse,
    ProxmoxClusterSummary,
    ProxmoxGuestSummary,
    ProxmoxNodeDetail,
    ProxmoxNodeRow,
    ProxmoxResourceRecord,
)
from netbox_proxbox.schemas._formatters import iter_node_records, iter_scalar_records

__all__ = (
    "build_cluster_summary",
    "build_guest_summary",
    "build_local_node_rows",
    "build_live_node_rows",
    "cluster_node_scope",
    "cluster_summary_from_node_rows",
    "get_endpoint_display_ip",
    "merge_node_rows",
)


def get_endpoint_display_ip(endpoint: ProxmoxEndpoint) -> str:
    """Return the display IP address for an endpoint."""
    if endpoint.domain:
        return endpoint.domain
    if endpoint.ip_address:
        return str(endpoint.ip_address.address).split("/")[0]
    return "—"


def build_cluster_summary(cluster_payload: object) -> dict[str, object]:
    response = ProxmoxClusterStatusResponse.model_validate(cluster_payload)
    return ProxmoxClusterSummary.from_status_response(response).model_dump()


def cluster_node_scope(
    cluster_payload: object,
) -> tuple[str | None, set[str]]:
    response = ProxmoxClusterStatusResponse.model_validate(cluster_payload)
    cluster_record = response.cluster_record
    cluster_name = (cluster_record.name or "").strip() if cluster_record else ""
    node_names = {
        record.name.strip()
        for record in response.node_records
        if isinstance(record.name, str) and record.name.strip()
    }
    return (cluster_name or None), node_names


def build_guest_summary(resources_payload: object) -> dict[str, object]:
    resource_records = [
        ProxmoxResourceRecord.model_validate(record)
        for record in iter_scalar_records(resources_payload)
    ]
    return ProxmoxGuestSummary.from_resources(resource_records).model_dump()


def build_local_node_rows(
    endpoint: ProxmoxEndpoint,
    *,
    cluster_name: str | None = None,
    cluster_node_names: set[str] | None = None,
) -> list[dict[str, object]]:
    endpoint_nodes = list(
        ProxmoxNode.objects.filter(endpoint=endpoint)
        .select_related("proxmox_cluster", "netbox_device")
        .order_by("name")
    )
    scoped_cluster_names = {
        node_name for node_name in (cluster_node_names or set()) if node_name
    }
    cluster_nodes: list[object] = []
    if cluster_name and scoped_cluster_names:
        cluster_nodes = list(
            ProxmoxNode.objects.filter(
                proxmox_cluster__name=cluster_name,
                name__in=sorted(scoped_cluster_names),
            )
            .select_related("proxmox_cluster", "netbox_device")
            .order_by("name")
        )

    nodes_by_name: dict[str, object] = {}
    for node in [*endpoint_nodes, *cluster_nodes]:
        node_name = str(getattr(node, "name", "") or "").strip()
        if not node_name or node_name in nodes_by_name:
            continue
        nodes_by_name[node_name] = node

    rows = [
        ProxmoxNodeRow.from_node_model(node).model_dump()
        for _, node in sorted(nodes_by_name.items())
    ]
    return rows


def build_live_node_rows(nodes_payload: object) -> list[dict[str, object]]:
    rows = [
        ProxmoxNodeRow.from_node_detail(
            ProxmoxNodeDetail.model_validate(record)
        ).model_dump()
        for record in iter_node_records(nodes_payload)
    ]
    return sorted(rows, key=lambda row: str(row["name"]))


def merge_node_rows(
    local_rows: list[dict[str, object]],
    live_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    live_rows_by_name = {
        str(row.get("name", "")): row for row in live_rows if row.get("name")
    }
    merged_rows: list[dict[str, object]] = []
    seen_names: set[str] = set()
    for row in local_rows:
        row_name = str(row.get("name", ""))
        live_row = live_rows_by_name.get(row_name)
        if live_row:
            merged_rows.append(row | live_row)
        else:
            merged_rows.append(row)
        if row_name:
            seen_names.add(row_name)

    for row in live_rows:
        row_name = str(row.get("name", ""))
        if row_name and row_name not in seen_names:
            merged_rows.append(row)

    return sorted(merged_rows, key=lambda row: str(row.get("name", "")))


def cluster_summary_from_node_rows(
    cluster_summary: dict[str, object],
    node_rows: list[dict[str, object]],
) -> dict[str, object]:
    if not node_rows:
        return cluster_summary

    online_nodes = sum(1 for row in node_rows if row.get("status") == "online")
    total_nodes = len(node_rows)
    return cluster_summary | {
        "nodes_total": total_nodes,
        "nodes_online": online_nodes,
        "nodes_offline": max(total_nodes - online_nodes, 0),
    }
