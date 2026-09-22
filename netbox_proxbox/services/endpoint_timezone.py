"""Best-effort discovery of a Proxmox endpoint's IANA timezone."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING
from urllib.parse import quote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests
from django.db import DatabaseError

from netbox_proxbox.services.backend_context import get_fastapi_request_context
from netbox_proxbox.views.backend_sync import proxmox_backend_name

if TYPE_CHECKING:
    from netbox_proxbox.models import ProxmoxEndpoint


logger = logging.getLogger(__name__)

ENDPOINT_TIMEZONE_TIMEOUT = 10
_IANA_TIMEZONE = re.compile(
    r"(?:[A-Za-z0-9_+.-]+/)+[A-Za-z0-9_+.-]+|UTC",
    re.ASCII,
)


def _endpoint_node_name(endpoint: ProxmoxEndpoint) -> str | None:
    """Choose a deterministic known node, preferring local and online nodes."""
    value = (
        endpoint.proxmox_nodes.order_by("-online", "-local", "pk")
        .values_list("name", flat=True)
        .first()
    )
    name = str(value or "").strip()
    return name or None


def _validated_iana_timezone(value: object) -> str | None:
    """Return a bounded IANA timezone identifier, or ``None`` for invalid input."""
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if len(candidate) > 64 or not _IANA_TIMEZONE.fullmatch(candidate):
        return None
    if any(part in {".", ".."} for part in candidate.split("/")):
        return None
    try:
        ZoneInfo(candidate)
    except (ValueError, ZoneInfoNotFoundError):
        return None
    return candidate


def discover_endpoint_timezone(
    endpoint: ProxmoxEndpoint,
    *,
    fastapi_endpoint_id: int | None = None,
    timeout: float = ENDPOINT_TIMEZONE_TIMEOUT,
) -> str | None:
    """Read one known node's timezone through proxbox-api's generated GET route."""
    if not bool(getattr(endpoint, "enabled", True)):
        return None
    node_name = _endpoint_node_name(endpoint)
    if node_name is None:
        return None
    context = get_fastapi_request_context(endpoint_id=fastapi_endpoint_id)
    if context is None or not context.http_url:
        return None
    url = (
        f"{context.http_url.rstrip('/')}/proxmox/api2/nodes/"
        f"{quote(node_name, safe='')}/time"
    )
    try:
        response = requests.get(
            url,
            params={
                "source": "database",
                "target_name": proxmox_backend_name(endpoint),
            },
            headers=context.headers or {},
            verify=bool(context.verify_ssl),
            timeout=max(0.001, min(float(timeout), ENDPOINT_TIMEZONE_TIMEOUT)),
            allow_redirects=False,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.exceptions.RequestException, TypeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    return _validated_iana_timezone(payload.get("timezone"))


def refresh_endpoint_timezone(
    endpoint: ProxmoxEndpoint,
    *,
    fastapi_endpoint_id: int | None = None,
    timeout: float = ENDPOINT_TIMEZONE_TIMEOUT,
) -> bool:
    """Discover and persist an endpoint timezone without firing save signals."""
    timezone_name = discover_endpoint_timezone(
        endpoint,
        fastapi_endpoint_id=fastapi_endpoint_id,
        timeout=timeout,
    )
    if timezone_name is None:
        return False
    try:
        updated = (
            type(endpoint)
            .objects.filter(pk=endpoint.pk)
            .update(iana_timezone=timezone_name)
        )
    except (AttributeError, DatabaseError):
        logger.warning(
            "Could not persist discovered timezone for Proxmox endpoint %s",
            getattr(endpoint, "pk", None),
        )
        return False
    return updated == 1
