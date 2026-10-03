"""CSV / JSON / YAML export helpers for ProxmoxEndpoint records."""

from netbox_proxbox.models import ProxmoxEndpoint
from typing import Any

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
        "site",
        "tenant",
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


def _sensitive_proxmox_material(endpoint: ProxmoxEndpoint, user: Any) -> dict[str, str]:
    """Resolve only authorized material without bypassing the selected provider."""
    from netbox_proxbox.integrations.openbao import (
        endpoint_uses_openbao_storage,
        resolve_endpoint_password,
        resolve_endpoint_token_value,
    )
    from netbox_proxbox.sensitive_data import require_sensitive_data_access

    require_sensitive_data_access(user)
    if not endpoint_uses_openbao_storage(endpoint):
        return {
            "password": endpoint.password or "",
            "token_value": endpoint.token_value or "",
        }
    return {
        "password": (
            resolve_endpoint_password(endpoint, user=user)
            if not endpoint.token_name or endpoint.openbao_password_credential_uuid
            else ""
        ),
        "token_value": (
            resolve_endpoint_token_value(endpoint, user=user)
            if endpoint.token_name or endpoint.openbao_token_credential_uuid
            else ""
        ),
    }


def _serialize_proxmox_endpoint(
    endpoint: ProxmoxEndpoint, include_sensitive: bool, *, user: Any = None
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
        "site": endpoint.site.slug if endpoint.site else "",
        "tenant": endpoint.tenant.slug if endpoint.tenant else "",
        "tags": tags_value,
        "token_name": endpoint.token_name or "",
    }
    if include_sensitive:
        row.update(_sensitive_proxmox_material(endpoint, user))
    return row
