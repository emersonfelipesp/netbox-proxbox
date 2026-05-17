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
    "append_unsynced_node_placeholders",
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
    from django.db.models import Q

    # Nodes directly linked OR in clusters owned by this endpoint (catches siblings
    # synced via a different ProxmoxEndpoint but belonging to the same cluster)
    endpoint_and_sibling_nodes = list(
        ProxmoxNode.objects.filter(
            Q(endpoint=endpoint) | Q(proxmox_cluster__endpoint=endpoint)
        )
        .select_related("proxmox_cluster", "netbox_device")
        .order_by("name")
    )
    # Nodes matching cluster name from the live API (cross-endpoint fallback).
    # Fires whenever the cluster name is known, even when the scoped
    # sibling-name set is empty — this covers freshly imported clusters that
    # have not yet linked any ProxmoxNode rows to this endpoint.
    scoped_cluster_names = {
        node_name for node_name in (cluster_node_names or set()) if node_name
    }
    name_matched_nodes: list[object] = []
    if cluster_name:
        name_filter_kwargs: dict[str, object] = {
            "proxmox_cluster__name": cluster_name,
        }
        if scoped_cluster_names:
            name_filter_kwargs["name__in"] = sorted(scoped_cluster_names)
        name_matched_nodes = list(
            ProxmoxNode.objects.filter(**name_filter_kwargs)
            .select_related("proxmox_cluster", "netbox_device")
            .order_by("name")
        )

    nodes_by_name: dict[str, object] = {}
    for node in [*endpoint_and_sibling_nodes, *name_matched_nodes]:
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

    rows_online = sum(1 for row in node_rows if row.get("status") == "online")
    rows_total = len(node_rows)

    # When the API summary already reports more members than we have rendered
    # rows for, the live rows are a strict subset of the cluster membership
    # (e.g. truncated `/cluster/status` payload, or members that have not been
    # synced yet). Preserve the API totals in that case so the dashboard panel
    # does not under-report the cluster size.
    api_total_raw = cluster_summary.get("nodes_total")
    api_online_raw = cluster_summary.get("nodes_online")
    api_total = api_total_raw if isinstance(api_total_raw, int) else 0
    api_online = api_online_raw if isinstance(api_online_raw, int) else 0

    if api_total > rows_total:
        resolved_total = api_total
        resolved_online = max(api_online, rows_online)
    else:
        resolved_total = rows_total
        resolved_online = rows_online

    return cluster_summary | {
        "nodes_total": resolved_total,
        "nodes_online": resolved_online,
        "nodes_offline": max(resolved_total - resolved_online, 0),
    }


def append_unsynced_node_placeholders(
    node_rows: list[dict[str, object]],
    cluster_node_names: set[str] | None,
) -> list[dict[str, object]]:
    """Append `status="unknown"` placeholder rows for cluster members not in node_rows.

    Cluster members named by the live API status payload that have no matching
    local `ProxmoxNode` (and no live row from `/nodes`) are otherwise invisible
    on the dashboard panel. This helper surfaces them with a distinguishing
    ``status="unknown"`` so operators can tell "synced and offline" apart from
    "not yet discovered".
    """
    if not cluster_node_names:
        return node_rows

    seen_names = {
        str(row.get("name", "")).strip()
        for row in node_rows
        if str(row.get("name", "")).strip()
    }
    placeholders = [
        {"name": member, "status": "unknown"}
        for member in sorted(name.strip() for name in cluster_node_names if name)
        if member and member not in seen_names
    ]
    if not placeholders:
        return node_rows
    return sorted(
        [*node_rows, *placeholders], key=lambda row: str(row.get("name", ""))
    )


def build_object_summaries(
    endpoint: ProxmoxEndpoint,
    netbox_cluster: Cluster | None,
) -> list[dict[str, object]]:
    """Return per-type counts of synced Proxmox objects for the dashboard.

    Objects scoped by endpoint (BackupRoutine, Replication) are always counted.
    Objects scoped by NetBox cluster (Storage, VMBackup, VMSnapshot, VirtualDisk)
    return zero counts when no cluster is linked yet.
    """
    from django.db.models import Count, Q

    from netbox_proxbox.choices import ReplicationStatusChoices

    summaries: list[dict[str, object]] = []

    br_stats = BackupRoutine.objects.filter(endpoint=endpoint).aggregate(
        total=Count("id"), enabled=Count("id", filter=Q(enabled=True))
    )
    br_total = br_stats["total"]
    br_enabled = br_stats["enabled"]
    summaries.append(
        {
            "label": "Backup Routines",
            "total": br_total,
            "detail": f"{br_enabled} enabled, {br_total - br_enabled} disabled",
            "list_url_name": "plugins:netbox_proxbox:backuproutine_list",
        }
    )

    rep_stats = Replication.objects.filter(endpoint=endpoint).aggregate(
        total=Count("id"),
        active=Count("id", filter=Q(status=ReplicationStatusChoices.ACTIVE)),
        stale=Count("id", filter=Q(status=ReplicationStatusChoices.STALE)),
    )
    summaries.append(
        {
            "label": "Replications",
            "total": rep_stats["total"],
            "detail": f"{rep_stats['active']} active, {rep_stats['stale']} stale",
            "list_url_name": "plugins:netbox_proxbox:replication_list",
        }
    )

    if netbox_cluster is not None:
        st_stats = ProxmoxStorage.objects.filter(cluster=netbox_cluster).aggregate(
            total=Count("id"),
            shared=Count("id", filter=Q(shared=True)),
            enabled=Count("id", filter=Q(enabled=True)),
        )
        st_total = st_stats["total"]
        summaries.append(
            {
                "label": "Storage",
                "total": st_total,
                "detail": f"{st_stats['shared']} shared, {st_total - st_stats['shared']} local, {st_stats['enabled']} enabled",
                "list_url_name": "plugins:netbox_proxbox:proxmoxstorage_list",
            }
        )

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
