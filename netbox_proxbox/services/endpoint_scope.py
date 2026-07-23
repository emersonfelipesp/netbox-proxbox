"""Helpers for scoping proxbox-api reads to enabled Proxmox endpoints."""

from __future__ import annotations

from netbox_proxbox.models import ProxmoxEndpoint
from netbox_proxbox.views.backend_sync import resolve_backend_endpoint_ids


def enabled_backend_endpoint_scope(
    *,
    base_url: str,
    auth_headers: dict[str, str] | None = None,
    backend_verify_ssl: bool = True,
    timeout: int = 15,
    endpoint_ids: list[int] | None = None,
) -> tuple[dict[str, str] | None, dict[int, int], str | None]:
    """Return proxbox-api query params for enabled Proxmox endpoints.

    The plugin stores NetBox-side primary keys, while proxbox-api filters sessions
    by its own endpoint table IDs. This helper performs that translation and
    returns ``None`` params when there are no endpoints in scope, so callers can
    skip the backend request instead of making an unscoped all-endpoint call.

    ``endpoint_ids`` narrows the scope to specific plugin ``ProxmoxEndpoint``
    primary keys — *not* backend wire ids, which are what this helper resolves.
    Omitting it (``None``) keeps the historic "every enabled endpoint" scope, for
    callers that genuinely have no selection to honour. An **empty list** is a
    resolved selection that matched nothing, and resolves to no scope at all —
    never to "all". That distinction is the whole point of the parameter: the
    backend reads a *missing* ``proxmox_endpoint_ids`` as "use every endpoint I
    hold", so silently widening an empty selection would send the widest request
    the API accepts precisely when the caller asked for the narrowest.
    """
    endpoint_filters: dict[str, object] = {"enabled": True}
    if endpoint_ids is not None:
        if not endpoint_ids:
            return None, {}, None
        endpoint_filters["pk__in"] = list(endpoint_ids)

    endpoints = list(ProxmoxEndpoint.objects.filter(**endpoint_filters))
    if not endpoints:
        return None, {}, None

    mapping, error = resolve_backend_endpoint_ids(
        endpoints,
        base_url=base_url,
        auth_headers=auth_headers,
        backend_verify_ssl=backend_verify_ssl,
        timeout=timeout,
    )
    if error:
        return None, {}, error

    backend_ids: list[str] = []
    for endpoint in endpoints:
        try:
            plugin_pk = int(getattr(endpoint, "pk"))
        except (TypeError, ValueError):
            continue
        backend_id = mapping.get(plugin_pk)
        if backend_id is not None:
            backend_ids.append(str(backend_id))
    if not backend_ids:
        return (
            None,
            mapping,
            "No enabled Proxmox endpoints are registered on the ProxBox backend.",
        )

    return (
        {
            "source": "database",
            "proxmox_endpoint_ids": ",".join(backend_ids),
        },
        mapping,
        None,
    )
