"""HTTP client helper that proxies Build-PVE-Template to proxbox-api.

The single ``FastAPIEndpoint`` row is the source of truth for the backend
URL and API key. The plugin posts the request body verbatim to
``POST /cloud/templates/pve`` on proxbox-api and returns the upstream
JSON / status pair to the caller.

Error handling mirrors ``services/backend_proxy.request_backend_resource``:
network errors and non-JSON responses surface as ``503`` with a ``detail``
field; upstream HTTP errors are propagated 1:1 so the NMS UI can render
the proxbox-api ``detail`` text directly.
"""

from __future__ import annotations

import logging
from typing import Any

import requests

from netbox_proxbox.services.backend_proxy import get_fastapi_request_context

logger = logging.getLogger("netbox_proxbox.api.build_pve_template")


def build_pve_template_via_backend(
    payload: dict[str, Any],
) -> tuple[dict[str, Any], int]:
    """Proxy a PVE template build request to proxbox-api.

    Returns the body + HTTP status that should be sent back to the caller
    of the NetBox plugin endpoint. Always returns JSON-serialisable data.
    """
    context = get_fastapi_request_context()
    http_url = getattr(context, "http_url", None)
    if not http_url:
        return (
            {
                "queued": False,
                "detail": "No FastAPIEndpoint configured for proxbox-api.",
            },
            503,
        )

    url = http_url.rstrip("/") + "/cloud/templates/pve"
    headers = dict(getattr(context, "headers", {}) or {})
    headers.setdefault("Content-Type", "application/json")
    verify_ssl = bool(getattr(context, "verify_ssl", True))

    try:
        response = requests.post(
            url,
            json=payload,
            headers=headers,
            verify=verify_ssl,
            timeout=(10, 600),
        )
    except requests.exceptions.RequestException as exc:
        logger.error("build-pve-template request to %s failed: %s", url, exc)
        return (
            {
                "queued": False,
                "detail": f"Could not reach proxbox-api at {url}: {exc}",
            },
            503,
        )

    try:
        body = response.json() if response.content else {}
    except ValueError:
        body = {"detail": response.text[:500]}

    if not isinstance(body, dict):
        body = {"result": body}
    return body, response.status_code
