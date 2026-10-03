"""CSV / JSON / YAML export helpers for NetBoxEndpoint records."""

from netbox_proxbox.models import NetBoxEndpoint
from typing import Any

__all__ = (
    "_netbox_export_fieldnames",
    "_serialize_netbox_endpoint",
)


def _netbox_export_fieldnames(include_sensitive: bool) -> tuple[str, ...]:
    """CSV/serialization column names; secrets columns only when ``include_sensitive``."""
    base_fields = (
        "id",
        "name",
        "domain",
        "ip_address",
        "port",
        "token_version",
        "verify_ssl",
        "tags",
    )
    if include_sensitive:
        return (
            *base_fields,
            "token",
            "token_key",
            "token_secret",
        )
    return base_fields


def _legacy_token_material(endpoint: NetBoxEndpoint) -> str:
    """Support v1 storage on all NetBox versions without treating a v2 key as a bearer."""
    token = endpoint.token
    if token is None or getattr(token, "version", 1) != 1:
        return ""
    return getattr(token, "plaintext", None) or getattr(token, "key", "") or ""


def _serialize_netbox_endpoint(
    endpoint: NetBoxEndpoint, include_sensitive: bool, *, user: Any = None
) -> dict[str, str]:
    """One export row as string values, optionally including token credentials."""
    tags_value = ",".join(sorted(tag.slug for tag in endpoint.tags.all()))
    row = {
        "id": str(endpoint.pk),
        "name": endpoint.name or "",
        "domain": endpoint.domain or "",
        "ip_address": str(endpoint.ip_address.address) if endpoint.ip_address else "",
        "port": str(endpoint.port),
        "token_version": endpoint.token_version or "",
        "verify_ssl": "true" if endpoint.verify_ssl else "false",
        "tags": tags_value,
    }
    if include_sensitive:
        from netbox_proxbox.sensitive_data import require_sensitive_data_access

        require_sensitive_data_access(user)
        row["token"] = _legacy_token_material(endpoint)
        row["token_key"] = endpoint.token_key or ""
        row["token_secret"] = endpoint.token_secret or ""
    return row
