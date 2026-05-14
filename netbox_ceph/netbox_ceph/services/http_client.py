"""HTTP client for proxbox-api ``/ceph/*`` read-only endpoints.

The companion ``proxbox-api`` backend exposes Ceph reflection routes as
plain JSON GETs (see ``proxbox_api/ceph/routes.py``):

- ``GET /ceph/status``
- ``GET /ceph/sync/full``
- ``GET /ceph/sync/{status,daemons,osds,pools,filesystems,crush,flags}``

Every ``/ceph/sync/*`` route accepts an optional ``netbox_branch_schema_id``
query parameter so the NetBox branching plugin can keep a single
branch-aware contract when persistence is added.

This module wraps those calls using the FastAPI endpoint context the
``netbox_proxbox`` plugin already resolves via
``services.backend_context.get_fastapi_request_context``. No new
authentication or endpoint resolution lives here.
"""

from __future__ import annotations

import logging
from typing import Any

import requests
from netbox_proxbox.services.backend_context import get_fastapi_request_context

logger = logging.getLogger("netbox_ceph.http_client")

CEPH_SYNC_RESOURCES: tuple[str, ...] = (
    "status",
    "daemons",
    "osds",
    "pools",
    "filesystems",
    "crush",
    "flags",
    "full",
)

# Match proxbox-api's tolerant read budget for long sync calls: short connect,
# long read. Ceph queries fan out across nodes and can take a while when
# clusters are large or degraded.
_CEPH_HTTP_TIMEOUT: tuple[float, float] = (5.0, 300.0)


class CephBackendError(RuntimeError):
    """Raised when the proxbox-api Ceph route returns an error or is unreachable."""


def _request_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def _resolve_context() -> tuple[str, dict[str, str], bool]:
    context = get_fastapi_request_context()
    if context is None or not context.http_url:
        raise CephBackendError(
            "No FastAPIEndpoint configured; cannot call proxbox-api /ceph/* routes."
        )
    return (
        context.http_url,
        dict(context.headers or {}),
        bool(context.verify_ssl),
    )


def _get_json(
    path: str,
    *,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    base_url, headers, verify_ssl = _resolve_context()
    url = _request_url(base_url, path)
    try:
        response = requests.get(
            url,
            headers=headers,
            params=params,
            timeout=_CEPH_HTTP_TIMEOUT,
            verify=verify_ssl,
        )
    except requests.RequestException as exc:
        raise CephBackendError(f"Ceph backend request failed: {exc}") from exc

    if response.status_code >= 400:
        raise CephBackendError(
            f"Ceph backend returned HTTP {response.status_code} for {path}: "
            f"{response.text[:500]}"
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise CephBackendError(
            f"Ceph backend returned non-JSON body for {path}: {exc}"
        ) from exc

    if not isinstance(payload, dict):
        raise CephBackendError(
            f"Ceph backend returned unexpected payload shape for {path} "
            f"(expected object, got {type(payload).__name__})"
        )
    return payload


def fetch_ceph_status() -> dict[str, Any]:
    """Return the ``/ceph/status`` reachability/health probe."""
    return _get_json("ceph/status")


def fetch_ceph_sync(
    resource: str,
    *,
    netbox_branch_schema_id: str | None = None,
) -> dict[str, Any]:
    """Call ``/ceph/sync/<resource>`` and return the parsed JSON payload."""
    if resource not in CEPH_SYNC_RESOURCES:
        raise ValueError(
            f"Unknown Ceph sync resource {resource!r}; "
            f"expected one of {CEPH_SYNC_RESOURCES}"
        )
    params: dict[str, Any] = {}
    if netbox_branch_schema_id:
        params["netbox_branch_schema_id"] = netbox_branch_schema_id
    return _get_json(f"ceph/sync/{resource}", params=params or None)
