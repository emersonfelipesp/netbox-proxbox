"""Fetch, cache, and summarize proxbox-api OpenAPI schema for NetBox UI."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import requests
from django.core.cache import cache

from netbox_proxbox.models import FastAPIEndpoint
from netbox_proxbox.utils import get_backend_auth_headers, get_fastapi_url

_CACHE_TIMEOUT_SECONDS = 60 * 60 * 24 * 30
_REQUEST_TIMEOUT_SECONDS = 10
_METHOD_ORDER = {
    "get": 10,
    "post": 20,
    "put": 30,
    "patch": 40,
    "delete": 50,
    "options": 60,
    "head": 70,
    "trace": 80,
}


def _request_json(
    url: str,
    *,
    headers: dict[str, str],
    verify_ssl: bool,
    timeout: int = _REQUEST_TIMEOUT_SECONDS,
) -> tuple[Any | None, str | None]:
    try:
        response = requests.get(
            url,
            headers=headers,
            verify=verify_ssl,
            timeout=timeout,
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as exc:
        return None, str(exc)

    try:
        return response.json(), None
    except ValueError as exc:
        return None, f"Invalid JSON response from {url}: {exc}"


def _backend_version(version_payload: Any) -> str:
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


def _normalize_servers(servers: Any) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    if not isinstance(servers, list):
        return normalized
    for item in servers:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        if not url:
            continue
        normalized.append(
            {
                "url": url,
                "description": str(item.get("description") or "").strip(),
            }
        )
    return normalized


def _normalize_tags(tags: Any) -> list[str]:
    normalized: list[str] = []
    if not isinstance(tags, list):
        return normalized
    for item in tags:
        if isinstance(item, dict):
            name = str(item.get("name") or "").strip()
            if name:
                normalized.append(name)
    return normalized


def _normalize_security_schemes(schemes: Any) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    if not isinstance(schemes, dict):
        return normalized
    for name, definition in schemes.items():
        if not isinstance(definition, dict):
            continue
        normalized.append(
            {
                "name": str(name),
                "type": str(definition.get("type") or ""),
                "scheme": str(definition.get("scheme") or ""),
                "in": str(definition.get("in") or ""),
            }
        )
    return sorted(normalized, key=lambda item: item["name"].lower())


def _normalize_operations(paths: Any) -> list[dict[str, Any]]:
    operations: list[dict[str, Any]] = []
    if not isinstance(paths, dict):
        return operations

    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            method_lower = str(method).lower().strip()
            if method_lower not in _METHOD_ORDER:
                continue
            if not isinstance(operation, dict):
                continue
            tags = operation.get("tags")
            tags_str = (
                ", ".join(str(tag) for tag in tags) if isinstance(tags, list) else ""
            )
            responses = operation.get("responses")
            parameters = operation.get("parameters")
            operations.append(
                {
                    "path": str(path),
                    "method": method_lower.upper(),
                    "method_order": _METHOD_ORDER[method_lower],
                    "summary": str(
                        operation.get("summary") or operation.get("description") or ""
                    ).strip(),
                    "operation_id": str(operation.get("operationId") or "").strip(),
                    "tags": tags_str,
                    "parameters_count": len(parameters)
                    if isinstance(parameters, list)
                    else 0,
                    "responses_count": len(responses)
                    if isinstance(responses, dict)
                    else 0,
                }
            )

    return sorted(operations, key=lambda item: (item["path"], item["method_order"]))


def _build_openapi_summary(
    openapi_payload: Any,
) -> tuple[dict[str, Any] | None, str | None]:
    if not isinstance(openapi_payload, dict):
        return None, "OpenAPI response is not a JSON object."

    info = openapi_payload.get("info")
    if not isinstance(info, dict):
        info = {}
    components = openapi_payload.get("components")
    if not isinstance(components, dict):
        components = {}

    paths = openapi_payload.get("paths")
    operations = _normalize_operations(paths)

    schemas = components.get("schemas")
    security_schemes = components.get("securitySchemes")

    summary: dict[str, Any] = {
        "title": str(info.get("title") or "OpenAPI"),
        "version": str(info.get("version") or "unknown"),
        "description": str(info.get("description") or "").strip(),
        "servers": _normalize_servers(openapi_payload.get("servers")),
        "tags": _normalize_tags(openapi_payload.get("tags")),
        "security_schemes": _normalize_security_schemes(security_schemes),
        "operations": operations,
        "stats": {
            "paths": len(paths) if isinstance(paths, dict) else 0,
            "operations": len(operations),
            "schemas": len(schemas) if isinstance(schemas, dict) else 0,
            "security_schemes": (
                len(security_schemes) if isinstance(security_schemes, dict) else 0
            ),
        },
    }
    return summary, None


def get_cached_openapi_schema(
    endpoint: FastAPIEndpoint, *, force_refresh: bool = False
) -> dict[str, Any]:
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

    summary, parse_error = _build_openapi_summary(openapi_payload)
    if parse_error:
        return {"error": parse_error}
    if summary is None:
        return {"error": "Unable to parse OpenAPI schema."}

    payload = {
        "backend_version": backend_version,
        "version_error": version_error,
        "schema": summary,
        "cache_hit": False,
        "cache_forced": force_refresh,
        "refreshed_at": datetime.now(timezone.utc).isoformat(),
    }
    cache.set(cache_key, payload, _CACHE_TIMEOUT_SECONDS)
    return payload
