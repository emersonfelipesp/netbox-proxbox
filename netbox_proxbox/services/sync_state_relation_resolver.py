"""Resolve current-run VM sync-state relations through native ownership."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
import json

from netbox_proxbox.models.sync_state import ProxboxVirtualMachineSyncState
from netbox_proxbox.services.sync_state_endpoint_backfill import (
    _ambiguous_claim_reasons,
    _endpoint_claims,
)


RESOLUTION_SAMPLE_LIMIT = 20


@dataclass(frozen=True, slots=True)
class EndpointRecord:
    """One endpoint and its authoritative native-cluster claim."""

    pk: int
    native_cluster_id: int | None


@dataclass(frozen=True, slots=True)
class ClusterRecord:
    """One locked Proxmox cluster tracking row."""

    pk: int
    endpoint_id: int
    name: str
    native_cluster_id: int | None


@dataclass(frozen=True, slots=True)
class NodeRecord:
    """One locked Proxmox node tracking row."""

    pk: int
    endpoint_id: int
    name: str
    cluster_id: int | None
    native_device_id: int | None


@dataclass(frozen=True, slots=True)
class SyncStateIdentity:
    """The relation-bearing identity copied from one VM sidecar."""

    pk: int
    virtual_machine_id: int
    endpoint_id: int | None
    backend_id: int
    node_id: int | None
    node_name: str
    cluster_id: int | None
    cluster_name: str
    native_cluster_id: int | None = None
    native_device_id: int | None = None


@dataclass(frozen=True, slots=True)
class RelationResolutionPlan:
    """Exact field changes and data-condition reasons for one sidecar."""

    updates: dict[str, int]
    reasons: tuple[str, ...]
    node_action: str | None = None
    cluster_action: str | None = None


@dataclass(frozen=True, slots=True)
class _RelationDecision:
    """One endpoint-scoped relation resolution result."""

    target_id: int | None
    uniquely_resolved: bool
    reason: str | None
    action: str | None


@dataclass(frozen=True, slots=True)
class _OwnershipDecision:
    """Native-cluster ownership proof and its linked tracking row."""

    approved: bool
    linked_cluster_id: int | None = None
    reason: str | None = None


@dataclass(frozen=True)
class RelationResolutionSummary:
    """Bounded, serializable result of one current-run resolution pass."""

    rows_examined: int
    rows_changed: int
    endpoints_bound: int
    nodes_bound: int
    nodes_rebound: int
    clusters_bound: int
    clusters_rebound: int
    skipped_backend_ids: dict[str, str]
    rows_with_unresolved_relations: int = 0
    unresolved: dict[str, dict[str, object]] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-compatible job-data representation."""
        return {
            "rows_examined": self.rows_examined,
            "rows_changed": self.rows_changed,
            "endpoints_bound": self.endpoints_bound,
            "nodes_bound": self.nodes_bound,
            "nodes_rebound": self.nodes_rebound,
            "clusters_bound": self.clusters_bound,
            "clusters_rebound": self.clusters_rebound,
            "skipped_backend_ids": dict(self.skipped_backend_ids),
            "unresolved": dict(self.unresolved),
            "rows_with_unresolved_relations": self.rows_with_unresolved_relations,
        }

    def one_line(self) -> str:
        """Return a stable one-line rendering for job logs."""
        return (
            "Current-run VM sync-state relation resolution: "
            f"rows_examined={self.rows_examined} rows_changed={self.rows_changed} "
            f"endpoints_bound={self.endpoints_bound} "
            f"nodes_bound={self.nodes_bound} nodes_rebound={self.nodes_rebound} "
            f"clusters_bound={self.clusters_bound} "
            f"clusters_rebound={self.clusters_rebound} "
            "skipped_backend_ids="
            f"{json.dumps(self.skipped_backend_ids, sort_keys=True)} "
            f"unresolved={json.dumps(self.unresolved, sort_keys=True)}"
        )


def current_run_endpoint_scope(
    backend_id_by_plugin_pk: Mapping[str, str],
) -> tuple[dict[int, int], dict[str, str]]:
    """Return unambiguous backend-id to plugin-pk authority for this run."""
    claims, skipped = _endpoint_claims(backend_id_by_plugin_pk)
    skipped.update(_ambiguous_claim_reasons(claims))
    resolved = {
        int(backend_id): int(next(iter(plugin_pks)))
        for backend_id, plugin_pks in claims.items()
        if backend_id not in skipped and len(plugin_pks) == 1
    }
    return resolved, skipped


def _records_by_id(records: Sequence[ClusterRecord | NodeRecord]) -> dict[int, object]:
    """Index locked relation records by primary key."""
    return {record.pk: record for record in records}


def _relation_contradicts_endpoint(
    relation_id: int | None,
    records_by_id: Mapping[int, object],
    endpoint_id: int,
) -> bool:
    """Return whether a present relation fails to belong to the endpoint."""
    if relation_id is None:
        return False
    record = records_by_id.get(relation_id)
    return record is None or getattr(record, "endpoint_id", None) != endpoint_id


def _target_decision(current_id: int | None, target_id: int) -> _RelationDecision:
    """Return the update action for one already-corroborated target."""
    if target_id == current_id:
        return _RelationDecision(target_id, True, None, None)
    action = "bound" if current_id is None else "rebound"
    return _RelationDecision(target_id, True, None, action)


def _resolve_name(
    *,
    relation_name: str,
    current_id: int | None,
    records: Sequence[ClusterRecord | NodeRecord],
    endpoint_id: int,
    kind: str,
) -> _RelationDecision:
    """Resolve one exact name within one endpoint without guessing."""
    name = relation_name.strip()
    if not name:
        return _RelationDecision(current_id, False, f"{kind}_name_missing", None)
    matches = [
        record
        for record in records
        if record.endpoint_id == endpoint_id and record.name == name
    ]
    if not matches:
        return _RelationDecision(current_id, False, f"{kind}_not_found", None)
    if len(matches) != 1:
        return _RelationDecision(current_id, False, f"{kind}_ambiguous", None)
    return _target_decision(current_id, matches[0].pk)


def _has_foreign_native_claim(
    native_cluster_id: int,
    plugin_endpoint_id: int,
    endpoint_records: Sequence[EndpointRecord],
    cluster_records: Sequence[ClusterRecord],
) -> bool:
    """Return whether another endpoint claims the VM's native cluster."""
    endpoint_claim = any(
        record.pk != plugin_endpoint_id
        and record.native_cluster_id == native_cluster_id
        for record in endpoint_records
    )
    tracking_claim = any(
        record.endpoint_id != plugin_endpoint_id
        and record.native_cluster_id == native_cluster_id
        for record in cluster_records
    )
    return endpoint_claim or tracking_claim


def _own_tracking_claims(
    native_cluster_id: int,
    plugin_endpoint_id: int,
    cluster_records: Sequence[ClusterRecord],
) -> tuple[list[ClusterRecord], bool]:
    """Return matching tracking rows and whether another native link conflicts."""
    own = [
        record
        for record in cluster_records
        if record.endpoint_id == plugin_endpoint_id
        and record.native_cluster_id == native_cluster_id
    ]
    conflict = any(
        record.endpoint_id == plugin_endpoint_id
        and record.native_cluster_id not in (None, native_cluster_id)
        for record in cluster_records
    )
    return own, conflict


def _native_cluster_ownership(
    row: SyncStateIdentity,
    *,
    plugin_endpoint_id: int,
    endpoint_records: Sequence[EndpointRecord],
    cluster_records: Sequence[ClusterRecord],
) -> _OwnershipDecision:
    """Corroborate the mapped endpoint through protected native ownership."""
    native_cluster_id = row.native_cluster_id
    if native_cluster_id is None:
        return _OwnershipDecision(False, reason="native_cluster_missing")
    endpoint_by_id = {record.pk: record for record in endpoint_records}
    mapped = endpoint_by_id.get(plugin_endpoint_id)
    if _has_foreign_native_claim(
        native_cluster_id,
        plugin_endpoint_id,
        endpoint_records,
        cluster_records,
    ):
        return _OwnershipDecision(False, reason="native_cluster_ownership_ambiguous")
    if mapped is None or mapped.native_cluster_id != native_cluster_id:
        return _OwnershipDecision(False, reason="native_cluster_not_owned_by_endpoint")
    own_linked, own_conflict = _own_tracking_claims(
        native_cluster_id,
        plugin_endpoint_id,
        cluster_records,
    )
    if own_conflict:
        return _OwnershipDecision(False, reason="native_cluster_not_owned_by_endpoint")
    if len(own_linked) > 1:
        return _OwnershipDecision(False, reason="native_cluster_ownership_ambiguous")
    linked_id = own_linked[0].pk if own_linked else None
    return _OwnershipDecision(True, linked_cluster_id=linked_id)


def _cluster_decision(
    row: SyncStateIdentity,
    *,
    plugin_endpoint_id: int,
    linked_cluster_id: int | None,
    cluster_records: Sequence[ClusterRecord],
) -> _RelationDecision:
    """Prefer the native-cluster tracking link over the recorded name."""
    if linked_cluster_id is None:
        return _resolve_name(
            relation_name=row.cluster_name,
            current_id=row.cluster_id,
            records=cluster_records,
            endpoint_id=plugin_endpoint_id,
            kind="cluster",
        )
    name = row.cluster_name.strip()
    named = [
        record
        for record in cluster_records
        if name and record.endpoint_id == plugin_endpoint_id and record.name == name
    ]
    if len(named) > 1:
        return _RelationDecision(row.cluster_id, False, "cluster_ambiguous", None)
    if named and named[0].pk != linked_cluster_id:
        return _RelationDecision(
            row.cluster_id,
            False,
            "cluster_name_contradicts_native_link",
            None,
        )
    return _target_decision(row.cluster_id, linked_cluster_id)


def _cluster_checked_node_decision(
    row: SyncStateIdentity,
    *,
    node: NodeRecord,
    resolved_cluster_id: int | None,
) -> _RelationDecision:
    """Return a node decision after checking its tracking cluster."""
    if node.cluster_id is not None and node.cluster_id != resolved_cluster_id:
        return _RelationDecision(row.node_id, False, "node_contradicts_cluster", None)
    return _target_decision(row.node_id, node.pk)


def _device_linked_node_decision(
    row: SyncStateIdentity,
    *,
    plugin_endpoint_id: int,
    resolved_cluster_id: int | None,
    node_records: Sequence[NodeRecord],
) -> _RelationDecision:
    """Resolve a node from the VM's native device and check its recorded name."""
    matches = [
        record
        for record in node_records
        if record.endpoint_id == plugin_endpoint_id
        and record.native_device_id == row.native_device_id
    ]
    if not matches:
        return _RelationDecision(
            row.node_id, False, "node_native_device_not_found", None
        )
    if len(matches) != 1:
        return _RelationDecision(
            row.node_id, False, "node_native_device_ambiguous", None
        )
    name = _resolve_name(
        relation_name=row.node_name,
        current_id=row.node_id,
        records=node_records,
        endpoint_id=plugin_endpoint_id,
        kind="node",
    )
    if name.uniquely_resolved and name.target_id != matches[0].pk:
        return _RelationDecision(
            row.node_id, False, "node_name_contradicts_native_device", None
        )
    return _cluster_checked_node_decision(
        row,
        node=matches[0],
        resolved_cluster_id=resolved_cluster_id,
    )


def _name_linked_node_decision(
    row: SyncStateIdentity,
    *,
    plugin_endpoint_id: int,
    resolved_cluster_id: int | None,
    node_records: Sequence[NodeRecord],
) -> _RelationDecision:
    """Allow name-only initial binding but never unverified node replacement."""
    decision = _resolve_name(
        relation_name=row.node_name,
        current_id=row.node_id,
        records=node_records,
        endpoint_id=plugin_endpoint_id,
        kind="node",
    )
    if not decision.uniquely_resolved or decision.target_id is None:
        return decision
    if row.node_id is not None and decision.target_id != row.node_id:
        return _RelationDecision(
            row.node_id,
            False,
            "node_unverified_drift_without_native_device",
            None,
        )
    node = next(record for record in node_records if record.pk == decision.target_id)
    return _cluster_checked_node_decision(
        row,
        node=node,
        resolved_cluster_id=resolved_cluster_id,
    )


def _node_decision(
    row: SyncStateIdentity,
    *,
    plugin_endpoint_id: int,
    resolved_cluster_id: int | None,
    node_records: Sequence[NodeRecord],
) -> _RelationDecision:
    """Resolve a node using native-device authority when available."""
    resolver = (
        _device_linked_node_decision
        if row.native_device_id is not None
        else _name_linked_node_decision
    )
    return resolver(
        row,
        plugin_endpoint_id=plugin_endpoint_id,
        resolved_cluster_id=resolved_cluster_id,
        node_records=node_records,
    )


def _relations_disagree(
    row: SyncStateIdentity,
    *,
    plugin_endpoint_id: int,
    node_records: Sequence[NodeRecord],
    cluster_records: Sequence[ClusterRecord],
) -> bool:
    """Return whether an existing relation contradicts the mapped endpoint."""
    return row.endpoint_id not in (None, plugin_endpoint_id) or any(
        (
            _relation_contradicts_endpoint(
                row.node_id, _records_by_id(node_records), plugin_endpoint_id
            ),
            _relation_contradicts_endpoint(
                row.cluster_id, _records_by_id(cluster_records), plugin_endpoint_id
            ),
        )
    )


def _plan_updates(
    row: SyncStateIdentity,
    plugin_endpoint_id: int,
    cluster: _RelationDecision,
    node: _RelationDecision,
) -> dict[str, int]:
    """Build exact sidecar relation updates from corroborated decisions."""
    updates: dict[str, int] = {}
    if row.endpoint_id is None:
        updates["endpoint_id"] = plugin_endpoint_id
    if cluster.action is not None and cluster.target_id is not None:
        updates["proxmox_cluster_id"] = cluster.target_id
    if node.action is not None and node.target_id is not None:
        updates["proxmox_node_id"] = node.target_id
    return updates


def plan_sync_state_relation_update(
    row: SyncStateIdentity,
    *,
    plugin_endpoint_id: int,
    endpoint_records: Sequence[EndpointRecord],
    node_records: Sequence[NodeRecord],
    cluster_records: Sequence[ClusterRecord],
) -> RelationResolutionPlan:
    """Plan one native-corroborated endpoint, cluster, and node update."""
    ownership = _native_cluster_ownership(
        row,
        plugin_endpoint_id=plugin_endpoint_id,
        endpoint_records=endpoint_records,
        cluster_records=cluster_records,
    )
    if not ownership.approved:
        return RelationResolutionPlan({}, (str(ownership.reason),))
    if _relations_disagree(
        row,
        plugin_endpoint_id=plugin_endpoint_id,
        node_records=node_records,
        cluster_records=cluster_records,
    ):
        return RelationResolutionPlan({}, ("relations_disagree",))
    cluster = _cluster_decision(
        row,
        plugin_endpoint_id=plugin_endpoint_id,
        linked_cluster_id=ownership.linked_cluster_id,
        cluster_records=cluster_records,
    )
    node = _node_decision(
        row,
        plugin_endpoint_id=plugin_endpoint_id,
        resolved_cluster_id=cluster.target_id if cluster.uniquely_resolved else None,
        node_records=node_records,
    )
    reasons = tuple(
        reason for reason in (cluster.reason, node.reason) if reason is not None
    )
    return RelationResolutionPlan(
        _plan_updates(row, plugin_endpoint_id, cluster, node),
        reasons,
        node_action=node.action,
        cluster_action=cluster.action,
    )


def _sidecar_values(queryset: object) -> list[SyncStateIdentity]:
    """Convert one sidecar values queryset into immutable identities."""
    values = queryset.values(
        "pk",
        "virtual_machine_id",
        "endpoint_id",
        "proxmox_endpoint_raw_id",
        "proxmox_node_id",
        "proxmox_node_name",
        "proxmox_cluster_id",
        "proxmox_cluster_name",
    )
    return [
        SyncStateIdentity(
            pk=int(row["pk"]),
            virtual_machine_id=int(row["virtual_machine_id"]),
            endpoint_id=(
                int(row["endpoint_id"]) if row["endpoint_id"] is not None else None
            ),
            backend_id=int(row["proxmox_endpoint_raw_id"]),
            node_id=(
                int(row["proxmox_node_id"])
                if row["proxmox_node_id"] is not None
                else None
            ),
            node_name=str(row["proxmox_node_name"] or ""),
            cluster_id=(
                int(row["proxmox_cluster_id"])
                if row["proxmox_cluster_id"] is not None
                else None
            ),
            cluster_name=str(row["proxmox_cluster_name"] or ""),
        )
        for row in values
    ]


def _candidate_rows(run_id: str, backend_ids: Sequence[int]) -> list[SyncStateIdentity]:
    """Read current-run candidates without taking locks out of order."""
    queryset = ProxboxVirtualMachineSyncState.objects.filter(
        last_run_id=run_id,
        proxmox_endpoint_raw_id__in=list(backend_ids),
    ).order_by("pk")
    return _sidecar_values(queryset)


def _vm_context(
    virtual_machine_ids: Sequence[int], *, lock: bool
) -> dict[int, tuple[int | None, int | None]]:
    """Read native VM cluster/device identity, optionally under row locks."""
    from virtualization.models import VirtualMachine

    queryset = VirtualMachine.objects.filter(pk__in=list(virtual_machine_ids)).order_by(
        "pk"
    )
    if lock:
        queryset = queryset.select_for_update()
    return {
        int(pk): (
            int(cluster_id) if cluster_id is not None else None,
            int(device_id) if device_id is not None else None,
        )
        for pk, cluster_id, device_id in queryset.values_list(
            "pk", "cluster_id", "device_id"
        )
    }


def _lock_endpoint_records(
    endpoint_ids: Sequence[int], native_cluster_ids: Sequence[int]
) -> list[EndpointRecord]:
    """Lock mapped endpoints and endpoint claims before native clusters."""
    from django.db.models import Q

    from netbox_proxbox.models.proxmox_endpoint import ProxmoxEndpoint

    rows = (
        ProxmoxEndpoint.objects.select_for_update()
        .filter(
            Q(pk__in=list(endpoint_ids)) | Q(netbox_cluster_id__in=native_cluster_ids)
        )
        .order_by("pk")
        .values_list("pk", "netbox_cluster_id")
    )
    return [
        EndpointRecord(
            pk=int(pk),
            native_cluster_id=(int(cluster_id) if cluster_id is not None else None),
        )
        for pk, cluster_id in rows
    ]


def _lock_native_clusters(native_cluster_ids: Sequence[int]) -> None:
    """Lock native clusters after endpoints and before tracking rows."""
    from virtualization.models import Cluster

    list(
        Cluster.objects.select_for_update()
        .filter(pk__in=list(native_cluster_ids))
        .order_by("pk")
        .values_list("pk", flat=True)
    )


def _endpoint_claim_records(
    endpoint_ids: Sequence[int], native_cluster_ids: Sequence[int]
) -> list[EndpointRecord]:
    """Re-read endpoint claims after native-cluster locks stabilize writers."""
    from django.db.models import Q

    from netbox_proxbox.models.proxmox_endpoint import ProxmoxEndpoint

    rows = (
        ProxmoxEndpoint.objects.filter(
            Q(pk__in=list(endpoint_ids)) | Q(netbox_cluster_id__in=native_cluster_ids)
        )
        .order_by("pk")
        .values_list("pk", "netbox_cluster_id")
    )
    return [
        EndpointRecord(
            pk=int(pk),
            native_cluster_id=(int(cluster_id) if cluster_id is not None else None),
        )
        for pk, cluster_id in rows
    ]


def _locked_cluster_records(
    rows: Sequence[SyncStateIdentity], endpoint_ids: Sequence[int]
) -> list[ClusterRecord]:
    """Lock native-linked, current, and exact-name tracking candidates."""
    from django.db.models import Q

    from netbox_proxbox.models.proxmox_cluster import ProxmoxCluster

    current_ids = {row.cluster_id for row in rows if row.cluster_id is not None}
    names = {row.cluster_name for row in rows if row.cluster_name}
    native_ids = {
        row.native_cluster_id for row in rows if row.native_cluster_id is not None
    }
    query = Q(pk__in=current_ids) | Q(netbox_cluster_id__in=native_ids)
    query |= Q(endpoint_id__in=endpoint_ids, name__in=names)
    query |= Q(endpoint_id__in=endpoint_ids, netbox_cluster_id__isnull=False)
    records = (
        ProxmoxCluster.objects.select_for_update()
        .filter(query)
        .order_by("pk")
        .values("pk", "endpoint_id", "name", "netbox_cluster_id")
    )
    return [
        ClusterRecord(
            pk=int(record["pk"]),
            endpoint_id=int(record["endpoint_id"]),
            name=str(record["name"]),
            native_cluster_id=(
                int(record["netbox_cluster_id"])
                if record["netbox_cluster_id"] is not None
                else None
            ),
        )
        for record in records
    ]


def _locked_node_records(
    rows: Sequence[SyncStateIdentity], endpoint_ids: Sequence[int]
) -> list[NodeRecord]:
    """Lock current, native-device, and exact-name nodes after tracking rows."""
    from django.db.models import Q

    from netbox_proxbox.models.proxmox_node import ProxmoxNode

    current_ids = {row.node_id for row in rows if row.node_id is not None}
    names = {row.node_name for row in rows if row.node_name}
    native_device_ids = {
        row.native_device_id for row in rows if row.native_device_id is not None
    }
    records = (
        ProxmoxNode.objects.select_for_update()
        .filter(
            Q(pk__in=current_ids)
            | Q(endpoint_id__in=list(endpoint_ids), name__in=names)
            | Q(
                endpoint_id__in=list(endpoint_ids),
                netbox_device_id__in=native_device_ids,
            )
        )
        .order_by("pk")
        .values(
            "pk",
            "endpoint_id",
            "name",
            "proxmox_cluster_id",
            "netbox_device_id",
        )
    )
    return [
        NodeRecord(
            pk=int(record["pk"]),
            endpoint_id=int(record["endpoint_id"]),
            name=str(record["name"]),
            cluster_id=(
                int(record["proxmox_cluster_id"])
                if record["proxmox_cluster_id"] is not None
                else None
            ),
            native_device_id=(
                int(record["netbox_device_id"])
                if record["netbox_device_id"] is not None
                else None
            ),
        )
        for record in records
    ]


def _locked_candidate_rows(
    candidate_pks: Sequence[int], run_id: str, backend_ids: Sequence[int]
) -> list[SyncStateIdentity]:
    """Lock sidecars last and revalidate their current-run identity."""
    queryset = (
        ProxboxVirtualMachineSyncState.objects.select_for_update()
        .filter(
            pk__in=list(candidate_pks),
            last_run_id=run_id,
            proxmox_endpoint_raw_id__in=list(backend_ids),
        )
        .order_by("pk")
    )
    return _sidecar_values(queryset)


def _with_vm_context(
    rows: Sequence[SyncStateIdentity],
    vm_context: Mapping[int, tuple[int | None, int | None]],
) -> list[SyncStateIdentity]:
    """Attach locked native VM placement to sidecar identities."""
    return [
        replace(
            row,
            native_cluster_id=vm_context.get(row.virtual_machine_id, (None, None))[0],
            native_device_id=vm_context.get(row.virtual_machine_id, (None, None))[1],
        )
        for row in rows
    ]


def _add_reason(reason_pks: dict[str, list[int]], reason: str, row_pk: int) -> None:
    """Record one row once in one bounded-reason source bucket."""
    bucket = reason_pks.setdefault(reason, [])
    if row_pk not in bucket:
        bucket.append(row_pk)


def _reason_summary(
    reason_pks: Mapping[str, Sequence[int]],
) -> dict[str, dict[str, object]]:
    """Build bounded reason counts and primary-key samples."""
    return {
        reason: {
            "count": len(pks),
            "sample_pks": list(pks[:RESOLUTION_SAMPLE_LIMIT]),
        }
        for reason, pks in sorted(reason_pks.items())
    }


def _guarded_update(
    row: SyncStateIdentity,
    run_id: str,
    updates: Mapping[str, int],
) -> int:
    """Apply one exact-PK update guarded by every sidecar identity field."""
    return int(
        ProxboxVirtualMachineSyncState.objects.filter(
            pk=row.pk,
            virtual_machine_id=row.virtual_machine_id,
            last_run_id=run_id,
            proxmox_endpoint_raw_id=row.backend_id,
            endpoint_id=row.endpoint_id,
            proxmox_node_id=row.node_id,
            proxmox_node_name=row.node_name,
            proxmox_cluster_id=row.cluster_id,
            proxmox_cluster_name=row.cluster_name,
        ).update(**dict(updates))
    )


def _empty_counts() -> dict[str, int]:
    """Return mutable counters for one resolution pass."""
    return {
        "rows_changed": 0,
        "endpoints_bound": 0,
        "nodes_bound": 0,
        "nodes_rebound": 0,
        "clusters_bound": 0,
        "clusters_rebound": 0,
    }


def _record_applied_plan(counts: dict[str, int], plan: RelationResolutionPlan) -> None:
    """Increment counters for one successfully applied plan."""
    counts["rows_changed"] += 1
    counts["endpoints_bound"] += int("endpoint_id" in plan.updates)
    if plan.node_action is not None:
        counts[f"nodes_{plan.node_action}"] += 1
    if plan.cluster_action is not None:
        counts[f"clusters_{plan.cluster_action}"] += 1


def _resolve_locked_rows(
    rows: Sequence[SyncStateIdentity],
    *,
    run_id: str,
    plugin_pk_by_backend_id: Mapping[int, int],
    endpoint_records: Sequence[EndpointRecord],
    node_records: Sequence[NodeRecord],
    cluster_records: Sequence[ClusterRecord],
    skipped: dict[str, str],
) -> RelationResolutionSummary:
    """Plan and apply every locked row while collecting bounded evidence."""
    counts = _empty_counts()
    reason_pks: dict[str, list[int]] = {}
    for row in rows:
        plan = plan_sync_state_relation_update(
            row,
            plugin_endpoint_id=plugin_pk_by_backend_id[row.backend_id],
            endpoint_records=endpoint_records,
            node_records=node_records,
            cluster_records=cluster_records,
        )
        for reason in plan.reasons:
            _add_reason(reason_pks, reason, row.pk)
        if not plan.updates:
            continue
        if _guarded_update(row, run_id, plan.updates) != 1:
            _add_reason(reason_pks, "guard_mismatch", row.pk)
            continue
        _record_applied_plan(counts, plan)
    return RelationResolutionSummary(
        rows_examined=len(rows),
        skipped_backend_ids=skipped,
        rows_with_unresolved_relations=len(
            {pk for pks in reason_pks.values() for pk in pks}
        ),
        unresolved=_reason_summary(reason_pks),
        **counts,
    )


def _resolve_in_transaction(
    plugin_pk_by_backend_id: Mapping[int, int],
    skipped: dict[str, str],
    run_id: str,
) -> RelationResolutionSummary:
    """Lock in cluster-binding order and resolve current-run sidecars."""
    backend_ids = sorted(plugin_pk_by_backend_id)
    endpoint_ids = sorted(set(plugin_pk_by_backend_id.values()))
    candidates = _candidate_rows(run_id, backend_ids)
    vm_ids = sorted({row.virtual_machine_id for row in candidates})
    initial_vm_context = _vm_context(vm_ids, lock=False)
    initial_native_ids = sorted(
        {
            cluster_id
            for cluster_id, _device_id in initial_vm_context.values()
            if cluster_id
        }
    )
    _lock_endpoint_records(endpoint_ids, initial_native_ids)
    locked_vm_context = _vm_context(vm_ids, lock=True)
    native_ids = sorted(
        {
            cluster_id
            for cluster_id, _device_id in locked_vm_context.values()
            if cluster_id
        }
    )
    _lock_native_clusters(native_ids)
    endpoint_records = _endpoint_claim_records(endpoint_ids, native_ids)
    contextual_candidates = _with_vm_context(candidates, locked_vm_context)
    cluster_records = _locked_cluster_records(contextual_candidates, endpoint_ids)
    node_records = _locked_node_records(contextual_candidates, endpoint_ids)
    rows = _locked_candidate_rows([row.pk for row in candidates], run_id, backend_ids)
    return _resolve_locked_rows(
        _with_vm_context(rows, locked_vm_context),
        run_id=run_id,
        plugin_pk_by_backend_id=plugin_pk_by_backend_id,
        endpoint_records=endpoint_records,
        node_records=node_records,
        cluster_records=cluster_records,
        skipped=skipped,
    )


def resolve_current_run_vm_sync_state_relations(
    backend_id_by_plugin_pk: Mapping[str, str],
    *,
    run_id: str,
) -> RelationResolutionSummary:
    """Resolve current-run VM relations after native ownership corroboration."""
    plugin_pk_by_backend_id, skipped = current_run_endpoint_scope(
        backend_id_by_plugin_pk
    )
    normalized_run_id = str(run_id).strip()
    if not normalized_run_id:
        skipped["<run>"] = "current run id is blank"
        return RelationResolutionSummary(0, 0, 0, 0, 0, 0, 0, skipped)
    if not plugin_pk_by_backend_id:
        return RelationResolutionSummary(0, 0, 0, 0, 0, 0, 0, skipped)

    from django.db import transaction

    with transaction.atomic():
        return _resolve_in_transaction(
            plugin_pk_by_backend_id, skipped, normalized_run_id
        )
