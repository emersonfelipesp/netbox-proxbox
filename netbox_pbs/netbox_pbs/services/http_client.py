"""HTTP client for proxbox-api ``/pbs/*`` endpoints."""

from __future__ import annotations

import logging
from typing import Any

import requests

from netbox_pbs.models import PBSPluginSettings

logger = logging.getLogger("netbox_pbs.http_client")

PBS_SYNC_RESOURCES: tuple[str, ...] = ("full", "datastores", "snapshots", "jobs", "node")

_PBS_HTTP_TIMEOUT: tuple[float, float] = (5.0, 300.0)


class PBSBackendError(RuntimeError):
    """Raised when proxbox-api PBS routes fail or cannot be reached."""


def _request_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def _auth_headers_from_key(api_key: str) -> dict[str, str]:
    value = api_key.strip()
    if not value:
        return {}
    if value.startswith(("Bearer ", "Token ")):
        return {"Authorization": value}
    return {"Authorization": f"Bearer {value}"}


def _resolve_context_from_netbox_proxbox() -> tuple[str, dict[str, str], bool] | None:
    try:
        from netbox_proxbox.services.backend_context import (  # noqa: PLC0415
            get_fastapi_request_context,
        )
    except ImportError:
        return None

    try:
        context = get_fastapi_request_context()
    except Exception:
        logger.exception("Could not resolve netbox-proxbox FastAPIEndpoint context")
        return None

    if context is None or not getattr(context, "http_url", None):
        return None
    return (
        str(context.http_url),
        dict(getattr(context, "headers", {}) or {}),
        bool(getattr(context, "verify_ssl", True)),
    )


def _resolve_context_from_settings() -> tuple[str, dict[str, str], bool]:
    settings_obj = PBSPluginSettings.get_solo()
    base_url = (getattr(settings_obj, "proxbox_api_url", "") or "").strip()
    if not base_url:
        raise PBSBackendError(
            "No proxbox-api URL configured. Install netbox-proxbox with a "
            "FastAPIEndpoint, or set PBS plugin settings proxbox_api_url."
        )
    headers = _auth_headers_from_key(getattr(settings_obj, "proxbox_api_key", "") or "")
    return base_url, headers, True


def _resolve_context(request: object | None = None) -> tuple[str, dict[str, str], bool]:
    del request
    proxbox_context = _resolve_context_from_netbox_proxbox()
    if proxbox_context is not None:
        return proxbox_context
    return _resolve_context_from_settings()


def _request_json(
    request: object | None,
    path: str,
    *,
    params: dict[str, Any] | None = None,
) -> Any:
    base_url, headers, verify_ssl = _resolve_context(request)
    url = _request_url(base_url, path)
    try:
        response = requests.get(
            url,
            headers=headers,
            params=params,
            timeout=_PBS_HTTP_TIMEOUT,
            verify=verify_ssl,
        )
    except requests.RequestException as exc:
        raise PBSBackendError(f"PBS backend request failed: {exc}") from exc

    if response.status_code >= 400:
        raise PBSBackendError(
            f"PBS backend returned HTTP {response.status_code} for {path}: "
            f"{response.text[:500]}"
        )

    try:
        return response.json()
    except ValueError as exc:
        raise PBSBackendError(f"PBS backend returned non-JSON body for {path}: {exc}") from exc


def get_pbs_status(request: object | None = None) -> dict[str, Any]:
    """Return the ``/pbs/status`` reachability snapshot."""

    payload = _request_json(request, "pbs/status")
    if not isinstance(payload, dict):
        raise PBSBackendError(
            "PBS status returned unexpected payload shape "
            f"(expected object, got {type(payload).__name__})"
        )
    return payload


def get_pbs_endpoints(request: object | None = None) -> list[dict[str, Any]]:
    """Return configured proxbox-api PBS endpoints from ``/pbs/endpoints``."""

    payload = _request_json(request, "pbs/endpoints")
    if not isinstance(payload, list):
        raise PBSBackendError(
            "PBS endpoints returned unexpected payload shape "
            f"(expected list, got {type(payload).__name__})"
        )
    return [item for item in payload if isinstance(item, dict)]


def sync_pbs_resource(
    request: object | None,
    resource: str,
    *,
    netbox_branch_schema_id: str | None = None,
) -> dict[str, Any]:
    """Call ``/pbs/sync/<resource>`` and return the parsed JSON payload."""

    if resource not in PBS_SYNC_RESOURCES:
        raise ValueError(
            f"Unknown PBS sync resource {resource!r}; expected one of {PBS_SYNC_RESOURCES}"
        )
    params: dict[str, Any] = {}
    if netbox_branch_schema_id:
        params["netbox_branch_schema_id"] = netbox_branch_schema_id
    payload = _request_json(request, f"pbs/sync/{resource}", params=params or None)
    if not isinstance(payload, dict):
        raise PBSBackendError(
            "PBS sync returned unexpected payload shape "
            f"(expected object, got {type(payload).__name__})"
        )
    return payload
