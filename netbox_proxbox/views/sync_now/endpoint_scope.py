"""Fail-closed Proxmox endpoint scoping for direct Sync Now actions."""

from __future__ import annotations

from netbox_proxbox.models import ProxmoxCluster
from netbox_proxbox.services.backend_context import get_fastapi_request_context
from netbox_proxbox.views.backend_sync import resolve_backend_endpoint_id


def _core_cluster_id(candidate: object | None) -> object | None:
    """Return the core ``virtualization.Cluster`` id carried by ``candidate``."""
    if candidate is None:
        return None

    # ``ProxmoxCluster.cluster_id`` is a Proxmox identifier, not the FK to the
    # linked core cluster.  Prefer its explicit NetBox relation and never fall
    # through to the similarly named Proxmox field when that relation exists.
    if hasattr(candidate, "netbox_cluster_id"):
        netbox_cluster_id = getattr(candidate, "netbox_cluster_id", None)
        if netbox_cluster_id:
            return netbox_cluster_id
        return getattr(getattr(candidate, "netbox_cluster", None), "pk", None)

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
    proxmox_cluster = getattr(target, "proxmox_cluster", None)
    netbox_device = getattr(target, "netbox_device", None)
    preferred = (
        (storage, virtual_machine) if prefer_storage else (virtual_machine, storage)
    )
    candidates = (proxmox_cluster, *preferred, target, netbox_device)
    for candidate in candidates:
        cluster_id = _core_cluster_id(candidate)
        if cluster_id:
            return cluster_id
    return None


def _direct_endpoint(target: object) -> object | None:
    """Return the endpoint directly recorded on cluster/node tracking rows."""
    return getattr(target, "endpoint", None)


def _disabled_owner_error() -> str:
    return (
        "The Proxmox endpoint that owns this object is disabled in NetBox. "
        "Enable that endpoint before syncing this object."
    )


def _missing_owner_error() -> str:
    return (
        "This object's NetBox cluster is not linked to a Proxmox endpoint, "
        "so its owning Proxmox estate cannot be determined. Sync cluster "
        "inventory first, then retry."
    )


def _resolve_enabled_owner(
    target: object,
    *,
    prefer_storage: bool,
) -> tuple[object | None, str | None, str | None]:
    """Return the sole enabled owner and its canonical cluster name."""
    direct_endpoint = _direct_endpoint(target)
    if direct_endpoint is not None and not bool(
        getattr(direct_endpoint, "enabled", False)
    ):
        return None, None, _disabled_owner_error()

    cluster_id = _target_core_cluster_id(target, prefer_storage=prefer_storage)
    if cluster_id:
        tracking_rows = list(
            ProxmoxCluster.objects.filter(netbox_cluster_id=cluster_id).select_related(
                "endpoint"
            )
        )
        enabled_rows = [
            row
            for row in tracking_rows
            if bool(getattr(getattr(row, "endpoint", None), "enabled", False))
        ]

        if not enabled_rows:
            if tracking_rows:
                return None, None, _disabled_owner_error()
            return None, None, _missing_owner_error()

        if len(enabled_rows) > 1:
            endpoint_ids = ", ".join(
                sorted(
                    str(getattr(getattr(row, "endpoint", None), "pk", "unknown"))
                    for row in enabled_rows
                )
            )
            return (
                None,
                None,
                (
                    "More than one enabled Proxmox cluster tracking row claims this "
                    f"object's NetBox cluster (endpoint ids {endpoint_ids}), so its "
                    "owning estate is ambiguous. Resolve the duplicate cluster "
                    "tracking rows before retrying."
                ),
            )

        tracking = enabled_rows[0]
        endpoint = getattr(tracking, "endpoint", None)
        if direct_endpoint is not None and getattr(
            direct_endpoint, "pk", None
        ) != getattr(endpoint, "pk", None):
            return (
                None,
                None,
                (
                    "The object's recorded Proxmox endpoint conflicts with the "
                    "endpoint that owns its linked NetBox cluster. Resolve the "
                    "cluster tracking records before retrying."
                ),
            )
        return endpoint, str(getattr(tracking, "name", "") or "") or None, None

    if direct_endpoint is not None:
        endpoint_pk = getattr(direct_endpoint, "pk", None)
        if endpoint_pk is None:
            return None, None, _missing_owner_error()
        proxmox_cluster = getattr(target, "proxmox_cluster", None)
        cluster_name = str(
            getattr(proxmox_cluster, "name", None)
            or getattr(target, "name", None)
            or ""
        )
        return direct_endpoint, cluster_name or None, None

    return (
        None,
        None,
        (
            "The Proxmox endpoint that owns this object could not be determined "
            "because it has no linked NetBox cluster."
        ),
    )


def resolve_target_proxmox_endpoint_scope(
    target: object,
    *,
    prefer_storage: bool = False,
) -> tuple[dict[str, object] | None, str | None, str | None]:
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
    endpoint, cluster_name, owner_error = _resolve_enabled_owner(
        target,
        prefer_storage=prefer_storage,
    )
    if endpoint is None:
        return None, None, owner_error

    context = get_fastapi_request_context()
    if context is None or not context.http_url:
        return (
            None,
            None,
            (
                "No enabled ProxBox backend is configured, so the owning Proxmox "
                "endpoint cannot be resolved for this sync."
            ),
        )

    backend_endpoint_id, resolve_error = resolve_backend_endpoint_id(
        endpoint,
        base_url=context.http_url.rstrip("/"),
        auth_headers=context.headers or {},
        backend_verify_ssl=bool(context.verify_ssl),
    )
    if backend_endpoint_id is None:
        return (
            None,
            None,
            resolve_error
            or (
                "The owning Proxmox endpoint is not registered on the selected "
                "ProxBox backend. Sync the endpoint registration, then retry."
            ),
        )

    scope: dict[str, object] = {
        "proxmox_endpoint_ids": str(backend_endpoint_id),
    }
    if context.endpoint_id is not None:
        scope["fastapi_endpoint_id"] = context.endpoint_id
    return scope, cluster_name, None
