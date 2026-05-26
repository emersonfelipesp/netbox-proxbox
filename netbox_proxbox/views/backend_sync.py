"""Helpers to synchronize NetBox endpoint records to proxbox-api backend storage."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import requests

from netbox_proxbox.models import ProxmoxEndpoint
from netbox_proxbox.utils import get_ip_address_host
from netbox_proxbox.views.error_utils import (
    extract_backend_error_detail,
    parse_requests_response_json,
)

if TYPE_CHECKING:
    from netbox_proxbox.models import NetBoxEndpoint

logger = logging.getLogger(__name__)


def proxmox_backend_name(endpoint: ProxmoxEndpoint) -> str:
    """Stable display name for proxbox-api including the NetBox primary key suffix."""
    base_name = (
        getattr(endpoint, "name", "") or "Proxmox Endpoint"
    ).strip() or "Proxmox Endpoint"
    endpoint_id = getattr(endpoint, "pk", getattr(endpoint, "id", None))
    return f"{base_name} (nb:{endpoint_id})" if endpoint_id is not None else base_name


def _related_object_metadata(
    prefix: str, value: object | None
) -> dict[str, object | None]:
    """Return flat relation metadata for proxbox-api endpoint placement fields."""
    if value is None:
        return {
            f"{prefix}_id": None,
            f"{prefix}_slug": None,
            f"{prefix}_name": None,
        }
    return {
        f"{prefix}_id": getattr(value, "pk", getattr(value, "id", None)),
        f"{prefix}_slug": getattr(value, "slug", None),
        f"{prefix}_name": getattr(value, "name", None) or str(value),
    }


def _int_or_none(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_or_none(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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
        "timeout": _int_or_none(getattr(endpoint, "timeout", None)),
        "max_retries": _int_or_none(getattr(endpoint, "max_retries", None)),
        "retry_backoff": _float_or_none(getattr(endpoint, "retry_backoff", None)),
        "token_name": (getattr(endpoint, "token_name", "") or "").strip() or None,
        "token_value": (getattr(endpoint, "token_value", "") or "").strip() or None,
        **_related_object_metadata("site", getattr(endpoint, "site", None)),
        **_related_object_metadata("tenant", getattr(endpoint, "tenant", None)),
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


def _netbox_endpoint_backend_payload(endpoint: NetBoxEndpoint) -> dict[str, object]:
    """JSON body for POST/PUT ``/netbox/endpoint`` from a ``NetBoxEndpoint`` row."""
    # Resolve IP address string — fall back to loopback when only a domain is set.
    ip_obj = getattr(endpoint, "ip_address", None)
    if ip_obj is not None:
        ip_address = str(ip_obj.address).split("/")[0]
    else:
        ip_address = "127.0.0.1"

    # Resolve token credentials from the endpoint model.
    token_version = getattr(endpoint, "effective_token_version", "v1") or "v1"
    token_key: str | None = None
    if token_version == "v2":
        # v2: secret goes in "token", key prefix goes in "token_key".
        token_value = (getattr(endpoint, "token_secret", "") or "").strip()
        raw_key = (getattr(endpoint, "token_key", "") or "").strip()
        # Fallback: if CharFields are empty but a FK token is linked, use its key.
        if not raw_key:
            token_obj = getattr(endpoint, "token", None)
            if token_obj is not None:
                raw_key = (getattr(token_obj, "key", "") or "").strip()
        token_key = raw_key or None
        if not token_value:
            logger.warning(
                "NetBoxEndpoint %s v2 token has no secret — backend will use an empty token",
                getattr(endpoint, "pk", None),
            )
    else:
        # v1: delegate to the model property which handles FK + plaintext fallback.
        token_value = (getattr(endpoint, "effective_token_value", None) or "") or ""
        if not token_value:
            logger.warning(
                "NetBoxEndpoint %s has no token configured — backend will use an empty token",
                getattr(endpoint, "pk", None),
            )

    payload: dict[str, object] = {
        "name": (getattr(endpoint, "name", "") or "NetBox Endpoint").strip()
        or "NetBox Endpoint",
        "ip_address": ip_address,
        "domain": (getattr(endpoint, "domain", "") or "").strip(),
        "port": int(getattr(endpoint, "port", 443) or 443),
        "verify_ssl": bool(getattr(endpoint, "verify_ssl", True)),
        "token_version": token_version,
        "token": token_value,
    }
    if token_key:
        payload["token_key"] = token_key
    return payload


def sync_netbox_endpoint_to_backend(
    endpoint: NetBoxEndpoint,
    *,
    base_url: str,
    auth_headers: dict[str, str] | None = None,
    backend_verify_ssl: bool = True,
    timeout: int = 10,
) -> tuple[bool, str | None, int | None]:
    """Ensure the NetBox endpoint configuration exists in the proxbox-api backend DB.

    Performs GET /netbox/endpoint to check for an existing entry, then PUT to
    update it or POST to create it.  Returns (success, error_message, http_status).
    """
    list_url = f"{base_url}/netbox/endpoint"
    headers = auth_headers or {}
    payload = _netbox_endpoint_backend_payload(endpoint)

    try:
        list_resp = requests.get(
            list_url,
            headers=headers,
            verify=backend_verify_ssl,
            timeout=timeout,
        )
        if list_resp.status_code != 200:
            return (
                False,
                f"Failed to list NetBox endpoints on backend: HTTP {list_resp.status_code}",
                list_resp.status_code,
            )

        existing, json_err = parse_requests_response_json(
            list_resp, log_label="netbox/endpoint"
        )
        if json_err:
            return (
                False,
                f"Failed to sync NetBox endpoint to ProxBox backend: {json_err}",
                None,
            )
        if not isinstance(existing, list):
            return (
                False,
                "ProxBox backend returned invalid NetBox endpoint list payload.",
                None,
            )

        if existing:
            # Singleton — always update the first (and only) entry.
            endpoint_id = (
                existing[0].get("id") if isinstance(existing[0], dict) else None
            )
            if endpoint_id is None:
                return (
                    False,
                    "proxbox-api returned NetBox endpoint without id, cannot update",
                    None,
                )
            response = requests.put(
                f"{list_url}/{endpoint_id}",
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

        if response.status_code in (200, 201):
            logger.info(
                "Synced NetBox endpoint '%s' to proxbox-api backend (HTTP %s)",
                payload.get("name"),
                response.status_code,
            )
            return True, None, None

        return (
            False,
            f"Failed to sync NetBox endpoint to proxbox-api: HTTP {response.status_code} — {response.text[:200]}",
            response.status_code,
        )

    except requests.exceptions.RequestException as exc:
        detail, http_status = extract_backend_error_detail(exc)
        return (
            False,
            f"Failed to sync NetBox endpoint to ProxBox backend: {detail}",
            http_status,
        )
