"""Release an endpoint's own cross-endpoint cluster tracking links left by old releases.

Releases before endpoint-scoped cluster discovery created one ``ProxmoxCluster``
tracking row on *every* endpoint for *every* discovered cluster, and an older
proxbox-api then linked every row whose name matched a native cluster. Each
endpoint can therefore hold several tracking rows linked to different native
clusters, which the native-cluster ownership model correctly refuses: every
tracking save fails with "Resolve this endpoint's conflicting tracking links
first." and every ``sync-cluster`` claim returns ``ClusterBindingConflict``.

This module performs the narrow, endpoint-local recovery. The only evidence it
accepts is the endpoint's own live, backend-scoped cluster discovery: exactly one
of the endpoint's linked tracking rows must carry the discovered cluster name.
Only the endpoint's *other* linked rows, which point at different native
clusters, are released by clearing their native link, together with the typed
cluster sidecar pointer that references a released row. Nothing is deleted, no
other endpoint's rows are written, and neither the endpoint authority nor any
native cluster changes. Every other ambiguity stays fail-closed for operator
review.
"""

from __future__ import annotations

import json
import logging
from typing import NamedTuple

from django.db import transaction

from netbox_proxbox.models import (
    ProxboxClusterSyncState,
    ProxmoxCluster,
    ProxmoxEndpoint,
)
from netbox_proxbox.services.connection_authority import connection_target_data

logger = logging.getLogger(__name__)


def discovery_target_identity(endpoint: ProxmoxEndpoint) -> str:
    """Return the endpoint's secret-free connection target as comparable text.

    Discovery evidence is only valid for the target it was read from. Callers
    capture this before the backend read and the release compares it again
    under the endpoint lock, so a target edited mid-discovery is refused.
    """
    return json.dumps(
        connection_target_data(endpoint), sort_keys=True, separators=(",", ":")
    )


class TrackingLink(NamedTuple):
    """One linked tracking row of the endpoint under repair."""

    pk: int
    name: str
    netbox_cluster_id: int


def plan_foreign_link_release(
    links: list[TrackingLink],
    live_cluster_name: str,
    authority_cluster_id: int | None,
) -> list[TrackingLink]:
    """Return the endpoint's linked rows to release, or nothing when unsafe.

    A release is planned only when the endpoint links more than one native
    cluster, exactly one linked row has the live discovered name, and the
    endpoint's authoritative native cluster is absent or equals that row's
    cluster. The kept cluster's rows are never released.
    """
    if not live_cluster_name:
        return []
    if len({link.netbox_cluster_id for link in links}) < 2:
        return []
    kept = [link for link in links if link.name == live_cluster_name]
    if len(kept) != 1:
        return []
    kept_cluster_id = kept[0].netbox_cluster_id
    if authority_cluster_id not in (None, kept_cluster_id):
        return []
    return [link for link in links if link.netbox_cluster_id != kept_cluster_id]


def _linked_rows(endpoint: ProxmoxEndpoint, *, lock: bool) -> list[TrackingLink]:
    queryset = ProxmoxCluster.objects.filter(
        endpoint=endpoint, netbox_cluster__isnull=False
    ).order_by("pk")
    if lock:
        queryset = queryset.select_for_update()
    return [
        TrackingLink(pk, name, cluster_id)
        for pk, name, cluster_id in queryset.values_list(
            "pk", "name", "netbox_cluster_id"
        )
    ]


def _lock_native_clusters(cluster_ids: set[int]) -> None:
    from virtualization.models import Cluster

    list(
        Cluster.objects.select_for_update()
        .filter(pk__in=sorted(cluster_ids))
        .order_by("pk")
        .values_list("pk", flat=True)
    )


def _release(endpoint: ProxmoxEndpoint, link: TrackingLink) -> int:
    """Clear one row's native link and the sidecar pointer that references it."""
    released = ProxmoxCluster.objects.filter(
        pk=link.pk, endpoint=endpoint, netbox_cluster_id=link.netbox_cluster_id
    ).update(netbox_cluster=None)
    if not released:
        return 0
    ProxboxClusterSyncState.objects.filter(
        cluster_id=link.netbox_cluster_id, proxmox_cluster_id=link.pk
    ).update(proxmox_cluster=None)
    logger.warning(
        "Released stale cross-endpoint tracking link: endpoint %s tracking row %s "
        "(%r) no longer links native cluster %s; live discovery reports a "
        "different cluster for this endpoint.",
        endpoint.pk,
        link.pk,
        link.name,
        link.netbox_cluster_id,
    )
    return released


def _target_unchanged(endpoint: ProxmoxEndpoint, discovered_target: str) -> bool:
    """Require the locked endpoint to still have the target discovery read from."""
    if discovered_target and discovery_target_identity(endpoint) == discovered_target:
        return True
    logger.info(
        "Skipped tracking-link release for endpoint %s: its connection target "
        "changed during discovery; the next run re-evaluates it.",
        endpoint.pk,
    )
    return False


def release_foreign_tracking_links(
    endpoint_id: int, live_cluster_name: str, discovered_target: str
) -> int:
    """Release this endpoint's tracking links to clusters it no longer reports.

    Runs in its own transaction so the release persists even when a later
    tracking save still conflicts with another endpoint's stale claim; that
    endpoint releases its own claim when its turn comes. Lock order follows the
    documented endpoint, native cluster, tracking row, sidecar sequence.
    ``discovered_target`` is the ``discovery_target_identity()`` captured before
    the backend read; a different target under the lock refuses the release.
    Returns the number of released tracking links.
    """
    with transaction.atomic():
        endpoint = ProxmoxEndpoint.objects.select_for_update().get(pk=endpoint_id)
        if not endpoint.enabled:
            return 0
        if not _target_unchanged(endpoint, discovered_target):
            return 0
        authority = endpoint.netbox_cluster_id
        candidates = _linked_rows(endpoint, lock=False)
        if not plan_foreign_link_release(candidates, live_cluster_name, authority):
            return 0
        locked_clusters = {link.netbox_cluster_id for link in candidates}
        if authority:
            locked_clusters.add(authority)
        _lock_native_clusters(locked_clusters)
        links = _linked_rows(endpoint, lock=True)
        if any(link.netbox_cluster_id not in locked_clusters for link in links):
            # A concurrent writer linked another cluster after the unlocked read;
            # leave the endpoint for the next run rather than lock out of order.
            return 0
        plan = plan_foreign_link_release(links, live_cluster_name, authority)
        list(
            ProxboxClusterSyncState.objects.select_for_update()
            .filter(proxmox_cluster_id__in=[link.pk for link in plan])
            .order_by("pk")
            .values_list("pk", flat=True)
        )
        return sum(_release(endpoint, link) for link in plan)
