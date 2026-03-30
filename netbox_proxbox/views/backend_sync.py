"""Helpers to synchronize NetBox endpoint records to proxbox-api backend storage."""

from __future__ import annotations

import requests

from netbox_proxbox.models import ProxmoxEndpoint
from netbox_proxbox.utils import get_ip_address_host
from netbox_proxbox.views.error_utils import (
    extract_backend_error_detail,
    parse_requests_response_json,
)


def proxmox_backend_name(endpoint: ProxmoxEndpoint) -> str:
    """Stable display name for proxbox-api including the NetBox primary key suffix."""
    base_name = (
        getattr(endpoint, "name", "") or "Proxmox Endpoint"
    ).strip() or "Proxmox Endpoint"
    endpoint_id = getattr(endpoint, "pk", getattr(endpoint, "id", None))
    return f"{base_name} (nb:{endpoint_id})" if endpoint_id is not None else base_name


def _proxmox_backend_payload(endpoint: ProxmoxEndpoint) -> dict[str, object]:
    """JSON body for POST/PUT ``/proxmox/endpoints`` from a ``ProxmoxEndpoint`` row."""
    return {
        "name": proxmox_backend_name(endpoint),
        "ip_address": get_ip_address_host(getattr(endpoint, "ip_address", None)),
        "domain": (getattr(endpoint, "domain", "") or "").strip() or None,
        "port": int(getattr(endpoint, "port", 8006) or 8006),
        "username": (getattr(endpoint, "username", "") or "root@pam").strip()
        or "root@pam",
        "password": (getattr(endpoint, "password", "") or "").strip() or None,
        "verify_ssl": bool(getattr(endpoint, "verify_ssl", False)),
        "token_name": (getattr(endpoint, "token_name", "") or "").strip() or None,
        "token_value": (getattr(endpoint, "token_value", "") or "").strip() or None,
    }


def sync_proxmox_endpoint_to_backend(
    endpoint: ProxmoxEndpoint,
    *,
    base_url: str,
    auth_headers: dict[str, str] | None = None,
    backend_verify_ssl: bool = True,
    timeout: int = 15,
) -> tuple[bool, str | None, int | None]:
    """Ensure the selected NetBox Proxmox endpoint exists in proxbox-api backend DB."""

    list_url = f"{base_url}/proxmox/endpoints"
    headers = auth_headers or {}
    payload = _proxmox_backend_payload(endpoint)

    try:
        list_response = requests.get(
            list_url,
            headers=headers,
            verify=backend_verify_ssl,
            timeout=timeout,
        )
        list_response.raise_for_status()
        endpoints, json_err = parse_requests_response_json(
            list_response, log_label="proxmox/endpoints"
        )
        if json_err:
            return (
                False,
                f"Failed to sync Proxmox endpoint to ProxBox backend: {json_err}",
                None,
            )
        if not isinstance(endpoints, list):
            return (
                False,
                "ProxBox backend returned invalid endpoint list payload.",
                None,
            )

        endpoint_name = str(payload["name"])
        existing = next(
            (
                item
                for item in endpoints
                if isinstance(item, dict) and item.get("name") == endpoint_name
            ),
            None,
        )

        if existing and existing.get("id") is not None:
            response = requests.put(
                f"{list_url}/{existing['id']}",
                json=payload,
                headers=headers,
                verify=backend_verify_ssl,
                timeout=timeout,
            )
        else:
            response = requests.post(
                list_url,
                json=payload,
                headers=headers,
                verify=backend_verify_ssl,
                timeout=timeout,
            )

        response.raise_for_status()
        return True, None, None

    except requests.exceptions.RequestException as exc:
        detail, http_status = extract_backend_error_detail(exc)
        return (
            False,
            f"Failed to sync Proxmox endpoint to ProxBox backend: {detail}",
            http_status,
        )
