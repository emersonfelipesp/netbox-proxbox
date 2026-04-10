"""CSV / JSON / YAML export helpers for ProxmoxEndpoint records."""

from netbox_proxbox.models import ProxmoxEndpoint

__all__ = (
    "_proxmox_export_fieldnames",
    "_serialize_proxmox_endpoint",
)


def _proxmox_export_fieldnames(include_sensitive: bool) -> tuple[str, ...]:
    """CSV/serialization column names; secrets columns only when ``include_sensitive``."""
    base_fields = (
        "id",
        "name",
        "domain",
        "ip_address",
        "port",
        "mode",
        "version",
        "repoid",
        "username",
        "verify_ssl",
        "tags",
    )
    if include_sensitive:
        return (
            *base_fields,
            "password",
            "token_name",
            "token_value",
        )
    return (
        *base_fields,
        "token_name",
    )


def _serialize_proxmox_endpoint(
    endpoint: ProxmoxEndpoint, include_sensitive: bool
) -> dict[str, str]:
    """One export row as string values, optionally including password and API token."""
    tags_value = ",".join(sorted(tag.slug for tag in endpoint.tags.all()))
    row = {
        "id": str(endpoint.pk),
        "name": endpoint.name or "",
        "domain": endpoint.domain or "",
        "ip_address": str(endpoint.ip_address.address) if endpoint.ip_address else "",
        "port": str(endpoint.port),
        "mode": endpoint.mode or "",
        "version": endpoint.version or "",
        "repoid": endpoint.repoid or "",
        "username": endpoint.username or "",
        "verify_ssl": "true" if endpoint.verify_ssl else "false",
        "tags": tags_value,
        "token_name": endpoint.token_name or "",
    }
    if include_sensitive:
        row["password"] = endpoint.password or ""
        row["token_value"] = endpoint.token_value or ""
    return row
