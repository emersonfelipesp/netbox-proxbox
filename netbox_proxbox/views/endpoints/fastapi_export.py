"""CSV / JSON / YAML export helpers for FastAPIEndpoint records."""

from netbox_proxbox.models import FastAPIEndpoint

__all__ = (
    "_fastapi_export_fieldnames",
    "_serialize_fastapi_endpoint",
)


def _fastapi_export_fieldnames(include_sensitive: bool) -> tuple[str, ...]:
    """CSV/serialization column names; secrets columns only when ``include_sensitive``."""
    base_fields = (
        "id",
        "name",
        "domain",
        "ip_address",
        "port",
        "verify_ssl",
        "use_websocket",
        "websocket_domain",
        "websocket_port",
        "server_side_websocket",
        "tags",
    )
    if include_sensitive:
        return (
            *base_fields,
            "token",
        )
    return base_fields


def _serialize_fastapi_endpoint(
    endpoint: FastAPIEndpoint, include_sensitive: bool
) -> dict[str, str]:
    """One export row as string values, optionally including the backend token."""
    tags_value = ",".join(sorted(tag.slug for tag in endpoint.tags.all()))
    row = {
        "id": str(endpoint.pk),
        "name": endpoint.name or "",
        "domain": endpoint.domain or "",
        "ip_address": str(endpoint.ip_address.address) if endpoint.ip_address else "",
        "port": str(endpoint.port),
        "verify_ssl": "true" if endpoint.verify_ssl else "false",
        "use_websocket": "true" if endpoint.use_websocket else "false",
        "websocket_domain": endpoint.websocket_domain or "",
        "websocket_port": str(endpoint.websocket_port),
        "server_side_websocket": "true" if endpoint.server_side_websocket else "false",
        "tags": tags_value,
    }
    if include_sensitive:
        row["token"] = endpoint.token or ""
    return row
