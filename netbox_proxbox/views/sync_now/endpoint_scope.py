"""Fail-closed Proxmox endpoint scoping for direct Sync Now actions."""

from __future__ import annotations

from netbox_proxbox.models import ProxmoxCluster
from netbox_proxbox.services.backend_context import get_fastapi_request_context
from netbox_proxbox.views.backend_sync import resolve_backend_endpoint_id


def _core_cluster_id(candidate: object | None) -> object | None:
    """Return the core ``virtualization.Cluster`` id carried by ``candidate``."""
    if candidate is None:
        return None
    cluster_id = getattr(candidate, "cluster_id", None)
    if cluster_id:
        return cluster_id
    return getattr(getattr(candidate, "cluster", None), "pk", None)


def _target_core_cluster_id(
    target: object,
    *,
    prefer_storage: bool,
) -> object | None:
    """Resolve the core cluster whose identifiers the direct request names.

    Backup parameters are derived from the backup's storage first. Snapshot and
    task-history parameters are derived from their VM first. Endpoint ownership
    must follow the same precedence or the scope can name a different estate
    from the query payload.
    """
    storage = getattr(target, "proxmox_storage", None)
    virtual_machine = getattr(target, "virtual_machine", None)
    candidates = (
        (storage, virtual_machine) if prefer_storage else (virtual_machine, storage)
    )
    for candidate in candidates:
        cluster_id = _core_cluster_id(candidate)
        if cluster_id:
            return cluster_id
    return None


def resolve_target_proxmox_endpoint_scope(
    target: object,
    *,
    prefer_storage: bool = False,
) -> tuple[dict[str, object] | None, str | None]:
    """Resolve one direct-action target to one enabled backend endpoint id.

    Proxmox cluster, node, and VM identifiers are unique only within an
    endpoint. The target's linked core cluster is therefore resolved through
    ``ProxmoxCluster.netbox_cluster`` rather than by cluster name. Exactly one
    enabled owning endpoint is required. Missing, disabled, or ambiguous
    ownership is returned as an operator-facing error before any sync request.

    The result contains keyword arguments for
    ``sync_individual_with_dependencies``. Supplying
    ``proxmox_endpoint_ids`` as a dedicated argument is load-bearing: the
    individual-sync service forwards it to the top-level request and every
    recursive dependency request.
    """
    cluster_id = _target_core_cluster_id(target, prefer_storage=prefer_storage)
    if not cluster_id:
        return None, (
            "The Proxmox endpoint that owns this object could not be determined "
            "because it has no linked NetBox cluster."
        )

    tracking_rows = list(
        ProxmoxCluster.objects.filter(netbox_cluster_id=cluster_id).select_related(
            "endpoint"
        )
    )
    enabled_endpoints: dict[str, object] = {}
    for tracking in tracking_rows:
        endpoint = getattr(tracking, "endpoint", None)
        endpoint_pk = getattr(endpoint, "pk", None)
        if endpoint_pk is None or not bool(getattr(endpoint, "enabled", False)):
            continue
        enabled_endpoints[str(endpoint_pk)] = endpoint

    if not enabled_endpoints:
        if tracking_rows:
            return None, (
                "The Proxmox endpoint that owns this object is disabled in "
                "NetBox. Enable that endpoint before syncing this object."
            )
        return None, (
            "This object's NetBox cluster is not linked to a Proxmox endpoint, "
            "so its owning Proxmox estate cannot be determined. Sync cluster "
            "inventory first, then retry."
        )

    if len(enabled_endpoints) > 1:
        endpoint_ids = ", ".join(sorted(enabled_endpoints))
        return None, (
            "More than one enabled Proxmox endpoint claims this object's "
            f"NetBox cluster (ids {endpoint_ids}), so its owning estate is "
            "ambiguous. Resolve the duplicate cluster tracking rows before "
            "retrying."
        )

    endpoint = next(iter(enabled_endpoints.values()))
    context = get_fastapi_request_context()
    if context is None or not context.http_url:
        return None, (
            "No enabled ProxBox backend is configured, so the owning Proxmox "
            "endpoint cannot be resolved for this sync."
        )

    backend_endpoint_id, resolve_error = resolve_backend_endpoint_id(
        endpoint,
        base_url=context.http_url.rstrip("/"),
        auth_headers=context.headers or {},
        backend_verify_ssl=bool(context.verify_ssl),
    )
    if backend_endpoint_id is None:
        return None, resolve_error or (
            "The owning Proxmox endpoint is not registered on the selected "
            "ProxBox backend. Sync the endpoint registration, then retry."
        )

    scope: dict[str, object] = {
        "proxmox_endpoint_ids": str(backend_endpoint_id),
    }
    if context.endpoint_id is not None:
        scope["fastapi_endpoint_id"] = context.endpoint_id
    return scope, None
