"""CSV / JSON / YAML export helpers for FastAPIEndpoint records."""

from typing import Any

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
        "use_https",
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


def _text(value: object) -> str:
    return "" if value is None else str(value)


def _boolean(value: object) -> str:
    return "true" if value else "false"


def _base_fastapi_row(endpoint: FastAPIEndpoint) -> dict[str, str]:
    address = getattr(endpoint.ip_address, "address", None)
    tags_value = ",".join(sorted(tag.slug for tag in endpoint.tags.all()))
    return {
        "id": _text(endpoint.pk),
        "name": _text(endpoint.name),
        "domain": _text(endpoint.domain),
        "ip_address": _text(address),
        "port": _text(endpoint.port),
        "use_https": _boolean(endpoint.use_https),
        "verify_ssl": _boolean(endpoint.verify_ssl),
        "use_websocket": _boolean(endpoint.use_websocket),
        "websocket_domain": _text(endpoint.websocket_domain),
        "websocket_port": (
            str(endpoint.websocket_port) if endpoint.websocket_port is not None else ""
        ),
        "server_side_websocket": _boolean(endpoint.server_side_websocket),
        "tags": tags_value,
    }


def _sensitive_token(endpoint: FastAPIEndpoint, user: Any) -> str:
    from netbox_proxbox.integrations.openbao_single import (
        owner_uses_openbao_storage,
        resolve_single_secret,
    )

    if owner_uses_openbao_storage(endpoint):
        return resolve_single_secret(endpoint, user=user)
    return _text(endpoint.token)


def _serialize_fastapi_endpoint(
    endpoint: FastAPIEndpoint,
    include_sensitive: bool,
    *,
    user: Any = None,
) -> dict[str, str]:
    """One export row as string values, optionally including the backend token."""
    row = _base_fastapi_row(endpoint)
    if include_sensitive:
        row["token"] = _sensitive_token(endpoint, user)
    return row
