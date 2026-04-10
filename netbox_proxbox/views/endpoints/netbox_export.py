"""CSV / JSON / YAML export helpers for NetBoxEndpoint records."""

from netbox_proxbox.models import NetBoxEndpoint

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
        "token",
        "tags",
    )
    if include_sensitive:
        return (
            *base_fields,
            "token_key",
            "token_secret",
        )
    return base_fields


def _serialize_netbox_endpoint(
    endpoint: NetBoxEndpoint, include_sensitive: bool
) -> dict[str, str]:
    """One export row as string values, optionally including token credentials."""
    tags_value = ",".join(sorted(tag.slug for tag in endpoint.tags.all()))
    token_key_str = endpoint.token.key if endpoint.token else ""
    row = {
        "id": str(endpoint.pk),
        "name": endpoint.name or "",
        "domain": endpoint.domain or "",
        "ip_address": str(endpoint.ip_address.address) if endpoint.ip_address else "",
        "port": str(endpoint.port),
        "token_version": endpoint.token_version or "",
        "verify_ssl": "true" if endpoint.verify_ssl else "false",
        "token": token_key_str,
        "tags": tags_value,
    }
    if include_sensitive:
        row["token_key"] = endpoint.token_key or ""
        row["token_secret"] = endpoint.token_secret or ""
    return row
