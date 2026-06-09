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
) -> tuple[dict[str, str] | None, dict[int, int], str | None]:
    """Return proxbox-api query params for all enabled Proxmox endpoints.

    The plugin stores NetBox-side primary keys, while proxbox-api filters sessions
    by its own endpoint table IDs. This helper performs that translation and
    returns ``None`` params when there are no enabled endpoints, so callers can
    skip the backend request instead of making an unscoped all-endpoint call.
    """
    endpoints = list(ProxmoxEndpoint.objects.filter(enabled=True))
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
