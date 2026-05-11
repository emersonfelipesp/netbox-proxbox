"""Fetch, cache, and summarize proxbox-api OpenAPI schema for NetBox UI."""

from __future__ import annotations

from datetime import datetime, timezone

import requests
from django.core.cache import cache

from netbox_proxbox.models import FastAPIEndpoint
from netbox_proxbox.schemas.openapi_schema import OpenAPISummary
from netbox_proxbox.services._endpoint_errors import translate_request_exception
from netbox_proxbox.utils import get_backend_auth_headers, get_fastapi_url

_CACHE_TIMEOUT_SECONDS = 60 * 60 * 24 * 30
_REQUEST_TIMEOUT_SECONDS = 10


def _request_json(
    url: str,
    *,
    headers: dict[str, str],
    verify_ssl: bool,
    timeout: int = _REQUEST_TIMEOUT_SECONDS,
) -> tuple[object | None, str | None]:
    try:
        response = requests.get(
            url,
            headers=headers,
            verify=verify_ssl,
            timeout=timeout,
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as exc:
        return None, translate_request_exception(exc)

    try:
        return response.json(), None
    except ValueError as exc:
        return None, f"Invalid JSON response from {url}: {exc}"


def _backend_version(version_payload: object) -> str:
    if isinstance(version_payload, dict):
        for key in ("version", "app_version", "backend_version"):
            value = version_payload.get(key)
            if value:
                return str(value)
    return "unknown"


def _openapi_cache_key(endpoint_id: int, backend_version: str) -> str:
    return (
        "netbox_proxbox:fastapi_openapi:"
        f"endpoint:{endpoint_id}:version:{backend_version}"
    )


def get_cached_openapi_schema(
    endpoint: FastAPIEndpoint, *, force_refresh: bool = False
) -> dict[str, object]:
    """Return parsed OpenAPI data for a FastAPI endpoint, cached by backend version."""
    endpoint_info = get_fastapi_url(endpoint) or {}
    http_url = endpoint_info.get("http_url")
    if not http_url:
        return {"error": "No FastAPI backend URL is configured."}

    verify_ssl = bool(endpoint_info.get("verify_ssl", True))
    headers = get_backend_auth_headers(endpoint)

    version_payload, version_error = _request_json(
        f"{http_url}/version",
        headers=headers,
        verify_ssl=verify_ssl,
    )
    backend_version = "unknown"
    if not version_error:
        backend_version = _backend_version(version_payload)

    cache_key = _openapi_cache_key(endpoint.pk, backend_version)
    cached = cache.get(cache_key)
    if isinstance(cached, dict) and not force_refresh:
        return {**cached, "cache_hit": True}

    openapi_payload, openapi_error = _request_json(
        f"{http_url}/openapi.json",
        headers=headers,
        verify_ssl=verify_ssl,
    )
    if openapi_error:
        return {"error": f"Unable to fetch /openapi.json: {openapi_error}"}

    try:
        summary = OpenAPISummary.from_raw_payload(openapi_payload)
    except ValueError as exc:
        return {"error": str(exc)}

    payload = {
        "backend_version": backend_version,
        "version_error": version_error,
        "schema": summary.model_dump(),
        "cache_hit": False,
        "cache_forced": force_refresh,
        "refreshed_at": datetime.now(timezone.utc).isoformat(),
    }
    cache.set(cache_key, payload, _CACHE_TIMEOUT_SECONDS)
    return payload
