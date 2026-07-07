"""HTTP client helper that proxies Cloud Image Build Pipeline requests.

The single ``FastAPIEndpoint`` row is the source of truth for the backend
URL and API key. The plugin posts the request body verbatim to
``POST /cloud/templates/images`` on proxbox-api and returns the upstream
JSON / status pair to the caller on success.

Error handling mirrors ``services/backend_proxy.request_backend_resource``:
network errors and non-JSON responses surface with a sanitized ``detail`` field;
upstream HTTP errors are normalized so raw proxbox-api response bodies are never
forwarded to the browser.
"""

from __future__ import annotations

import logging
from typing import Any

import requests

from netbox_proxbox.services.backend_proxy import get_fastapi_request_context
from netbox_proxbox.views.error_utils import (
    extract_backend_error_detail,
    parse_requests_response_json,
)

logger = logging.getLogger("netbox_proxbox.api.build_pve_template")


def build_cloud_image_pipeline_via_backend(
    payload: dict[str, Any],
) -> tuple[dict[str, Any], int]:
    """Proxy a Cloud Image Build Pipeline request to proxbox-api.

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

    url = http_url.rstrip("/") + "/cloud/templates/images"
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
        logger.error("cloud image build pipeline request to %s failed: %s", url, exc)
        return (
            {
                "queued": False,
                "detail": f"Could not reach proxbox-api at {url}: {exc}",
            },
            503,
        )

    if response.status_code >= 400:
        try:
            response.raise_for_status()
        except requests.exceptions.RequestException as exc:
            detail, status = extract_backend_error_detail(exc)
        else:
            detail, status = (
                f"Backend returned HTTP {response.status_code} without a JSON error detail.",
                response.status_code,
            )
        return {"queued": False, "detail": detail}, status or response.status_code

    body, json_err = parse_requests_response_json(
        response, log_label="cloud-image-build"
    )
    if json_err:
        return {"queued": False, "detail": json_err}, 502

    if not isinstance(body, dict):
        body = {"result": body}
    return body, response.status_code


def build_pve_template_via_backend(
    payload: dict[str, Any],
) -> tuple[dict[str, Any], int]:
    """Backward-compatible helper for the original PVE-only action."""
    payload = {**payload, "product_type": "pve"}
    return build_cloud_image_pipeline_via_backend(payload)
