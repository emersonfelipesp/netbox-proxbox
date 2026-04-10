"""Data-building helpers extracted from the dashboard view."""

from __future__ import annotations

from virtualization.models import Cluster

from netbox_proxbox.models import (
    BackupRoutine,
    ProxmoxEndpoint,
    ProxmoxNode,
    ProxmoxStorage,
    ProxmoxStorageVirtualDisk,
    Replication,
    VMBackup,
    VMSnapshot,
)
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
    "build_object_summaries",
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
    # Query 1: nodes directly linked to this endpoint
    endpoint_nodes = list(
        ProxmoxNode.objects.filter(endpoint=endpoint)
        .select_related("proxmox_cluster", "netbox_device")
        .order_by("name")
    )
    # Query 2: nodes in clusters owned by this endpoint (catches siblings synced
    # via a different ProxmoxEndpoint but belonging to the same cluster)
    cluster_sibling_nodes = list(
        ProxmoxNode.objects.filter(proxmox_cluster__endpoint=endpoint)
        .select_related("proxmox_cluster", "netbox_device")
        .order_by("name")
    )
    # Query 3: nodes matching cluster name from the live API (cross-endpoint fallback)
    scoped_cluster_names = {
        node_name for node_name in (cluster_node_names or set()) if node_name
    }
    name_matched_nodes: list[object] = []
    if cluster_name and scoped_cluster_names:
        name_matched_nodes = list(
            ProxmoxNode.objects.filter(
                proxmox_cluster__name=cluster_name,
                name__in=sorted(scoped_cluster_names),
            )
            .select_related("proxmox_cluster", "netbox_device")
            .order_by("name")
        )

    nodes_by_name: dict[str, object] = {}
    for node in [*endpoint_nodes, *cluster_sibling_nodes, *name_matched_nodes]:
        node_name = str(getattr(node, "name", "") or "").strip()
        if not node_name or node_name in nodes_by_name:
            continue
        nodes_by_name[node_name] = node

    return [
        ProxmoxNodeRow.from_node_model(node).model_dump()
        for _, node in sorted(nodes_by_name.items())
    ]


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


def build_object_summaries(
    endpoint: ProxmoxEndpoint,
    netbox_cluster: Cluster | None,
) -> list[dict[str, object]]:
    """Return per-type counts of synced Proxmox objects for the dashboard.

    Objects scoped by endpoint (BackupRoutine, Replication) are always counted.
    Objects scoped by NetBox cluster (Storage, VMBackup, VMSnapshot, VirtualDisk)
    return zero counts when no cluster is linked yet.
    """
    summaries: list[dict[str, object]] = []

    # --- Backup Routines (scoped by endpoint) ---
    br_qs = BackupRoutine.objects.filter(endpoint=endpoint)
    br_total = br_qs.count()
    br_enabled = br_qs.filter(enabled=True).count()
    summaries.append(
        {
            "label": "Backup Routines",
            "total": br_total,
            "detail": f"{br_enabled} enabled, {br_total - br_enabled} disabled",
            "list_url_name": "plugins:netbox_proxbox:backuproutine_list",
        }
    )

    # --- Replications (scoped by endpoint) ---
    rep_qs = Replication.objects.filter(endpoint=endpoint)
    rep_total = rep_qs.count()
    rep_active = rep_qs.filter(status="active").count()
    rep_stale = rep_qs.filter(status="stale").count()
    summaries.append(
        {
            "label": "Replications",
            "total": rep_total,
            "detail": f"{rep_active} active, {rep_stale} stale",
            "list_url_name": "plugins:netbox_proxbox:replication_list",
        }
    )

    # --- Storage (scoped by NetBox cluster) ---
    if netbox_cluster is not None:
        st_qs = ProxmoxStorage.objects.filter(cluster=netbox_cluster)
        st_total = st_qs.count()
        st_shared = st_qs.filter(shared=True).count()
        st_enabled = st_qs.filter(enabled=True).count()
        summaries.append(
            {
                "label": "Storage",
                "total": st_total,
                "detail": f"{st_shared} shared, {st_total - st_shared} local, {st_enabled} enabled",
                "list_url_name": "plugins:netbox_proxbox:proxmoxstorage_list",
            }
        )

        # --- VM Backups (scoped via storage → cluster) ---
        vb_total = VMBackup.objects.filter(
            proxmox_storage__cluster=netbox_cluster
        ).count()
        summaries.append(
            {
                "label": "VM Backups",
                "total": vb_total,
                "detail": None,
                "list_url_name": "plugins:netbox_proxbox:vmbackup_list",
            }
        )

        # --- VM Snapshots (scoped via storage → cluster) ---
        vs_total = VMSnapshot.objects.filter(
            proxmox_storage__cluster=netbox_cluster
        ).count()
        summaries.append(
            {
                "label": "VM Snapshots",
                "total": vs_total,
                "detail": None,
                "list_url_name": "plugins:netbox_proxbox:vmsnapshot_list",
            }
        )

        # --- Virtual Disks (scoped via storage → cluster) ---
        vd_total = ProxmoxStorageVirtualDisk.objects.filter(
            proxmox_storage__cluster=netbox_cluster
        ).count()
        summaries.append(
            {
                "label": "Virtual Disks",
                "total": vd_total,
                "detail": None,
                "list_url_name": "plugins:netbox_proxbox:virtual_disks",
            }
        )

    return summaries
