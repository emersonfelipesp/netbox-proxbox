"""Individual sync service for calling proxbox-api individual sync endpoints."""

from __future__ import annotations

import logging

import requests

from netbox_proxbox.utils import get_first_fastapi_context

logger = logging.getLogger(__name__)

_INDIVIDUAL_SYNC_TIMEOUT = 30
_CONTEXT_KEYS = ("cluster_name", "node", "type", "vmid", "storage_name")


def sync_individual(
    path: str,
    query_params: dict | None = None,
) -> tuple[dict, int]:
    """Call an individual sync endpoint on proxbox-api.

    Args:
        path: The API path (e.g., "sync/individual/vm")
        query_params: Query parameters for the endpoint

    Returns:
        Tuple of (response_dict, status_code)
    """
    context = get_first_fastapi_context()
    if context is None or not context.get("http_url"):
        return {"error": "No FastAPI endpoint configured."}, 503

    http_url = context["http_url"]
    headers = context.get("headers") or {}
    verify_ssl = context.get("verify_ssl", True)

    url = f"{http_url}/{path}"
    request_candidates = [(url, verify_ssl)]

    fallback_url = context.get("ip_address_url")
    if fallback_url:
        fallback_path = f"{fallback_url}/{path}"
        if fallback_path != url:
            request_candidates.append((fallback_path, verify_ssl))

    last_error = None
    for request_url, verify in request_candidates:
        try:
            response = requests.get(
                request_url,
                params=query_params,
                headers=headers,
                verify=verify,
                timeout=_INDIVIDUAL_SYNC_TIMEOUT,
            )
            response.raise_for_status()
            return response.json(), 200
        except requests.exceptions.RequestException as exc:
            last_error = str(exc)
            logger.error(
                "Individual sync request failed for %s via %s: %s",
                path,
                request_url,
                exc,
            )
            if getattr(exc, "response", None) is not None:
                break
        except Exception as exc:  # pragma: no cover
            last_error = str(exc)
            logger.error("Unexpected error in individual sync for %s: %s", path, exc)

    return {"error": last_error or "Unable to reach the ProxBox backend."}, 503


def _build_cache_key(path: str, query_params: dict | None) -> str:
    """Build a deterministic key for recursion cycle detection."""
    normalized = query_params or {}
    sorted_items = tuple(sorted((str(k), str(v)) for k, v in normalized.items()))
    return f"{path}:{sorted_items}"


def _merge_context(base: dict | None, update: dict | None) -> dict:
    """Merge dependency context while ignoring empty values."""
    merged: dict[str, object] = dict(base or {})
    for key in _CONTEXT_KEYS:
        value = (update or {}).get(key)
        if value not in (None, ""):
            merged[key] = value
    return merged


def sync_individual_with_dependencies(
    path: str,
    query_params: dict | None = None,
    _visited: set | None = None,
    _context: dict | None = None,
) -> tuple[dict, int, list[dict]]:
    """Call an individual sync endpoint and recursively sync dependencies.

    Args:
        path: The API path (e.g., "sync/individual/vm")
        query_params: Query parameters for the endpoint
        _visited: Internal tracker to prevent circular dependency syncs

    Returns:
        Tuple of (response_dict, status_code, list of synced dependencies)
    """
    if _visited is None:
        _visited = set()

    params = dict(query_params or {})
    context = _merge_context(_context, params)
    for key in _CONTEXT_KEYS:
        if key not in params and key in context:
            params[key] = context[key]

    cache_key = _build_cache_key(path, params)
    if cache_key in _visited:
        return {}, 200, []
    _visited.add(cache_key)

    response, status = sync_individual(path, params)
    all_synced = []

    if status == 200 and isinstance(response, dict):
        dependencies = response.get("dependencies_synced", [])
        for dep in dependencies:
            dep_type = dep.get("object_type")
            action = dep.get("action")
            if action in ("created", "updated"):
                dep_response, dep_status, dep_synced = _sync_dependency(
                    dep, _visited, context
                )
                all_synced.extend(dep_synced)
                if dep_response:
                    all_synced.append(
                        {
                            "object_type": dep_type,
                            "response": dep_response,
                            "status": dep_status,
                        }
                    )

    return response, status, all_synced


def _get_dependency_config(
    dep_type: str,
) -> tuple[str, dict | None] | None:
    """Return (path, param_keys) for a dependency type, or None if unknown."""
    DEPENDENCY_CONFIG = {
        "cluster": ("sync/individual/cluster", ("name",)),
        "node": ("sync/individual/node", ("cluster_name", "node_name")),
        "vm": ("sync/individual/vm", ("cluster_name", "node", "type", "vmid")),
        "storage": ("sync/individual/storage", ("cluster_name", "storage_name")),
    }
    return DEPENDENCY_CONFIG.get(dep_type)


def _sync_dependency(
    dep: dict, _visited: set, parent_context: dict | None
) -> tuple[dict, int, list[dict]]:
    """Sync a single dependency from a dependencies_synced entry."""
    dep_type = dep.get("object_type")
    if not dep_type:
        return {}, 200, []

    config = _get_dependency_config(dep_type)
    if config is None:
        return {}, 200, []

    path, param_keys = config
    context = _merge_context(parent_context, dep)

    params = {}
    for key in param_keys:
        if key == "name":
            params[key] = dep.get("name") or context.get(f"{dep_type}_name", "")
        elif key == "cluster_name":
            params[key] = dep.get("cluster_name") or context.get("cluster_name", "")
        elif key == "node_name":
            params[key] = dep.get("name") or ""
        elif key == "node":
            params[key] = dep.get("node") or context.get("node", "")
        elif key == "type":
            params[key] = dep.get("type") or context.get("type", "qemu")
        elif key == "vmid":
            params[key] = dep.get("vmid") or context.get("vmid")
        elif key == "storage_name":
            params[key] = dep.get("name") or context.get("storage_name", "")

    return sync_individual_with_dependencies(path, params, _visited, _context=context)


def sync_backup_routines_individual(
    cluster_name: str | None = None,
) -> tuple[dict, int]:
    """Sync backup routines for a specific cluster.

    Args:
        cluster_name: Optional cluster name to filter routines.

    Returns:
        Tuple of (response_dict, status_code)
    """
    query_params = {}
    if cluster_name:
        query_params["cluster_name"] = cluster_name
    return sync_individual("sync/individual/backup-routines", query_params)
