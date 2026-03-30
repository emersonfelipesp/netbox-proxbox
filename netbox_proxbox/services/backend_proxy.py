"""HTTP and SSE proxy helpers for the external ProxBox FastAPI backend."""

from __future__ import annotations

import json
import logging
from collections.abc import Generator
from typing import Any

import requests

from netbox_proxbox.models import FastAPIEndpoint
from netbox_proxbox.type_defs import BackendRequestContext
from netbox_proxbox.utils import get_backend_auth_headers, get_fastapi_url
from netbox_proxbox.views.error_utils import extract_backend_error_detail

logger = logging.getLogger(__name__)

# proxbox-api awaits the full backup sync in one GET; allow long read like the stream proxy.
_LONG_RUNNING_BACKUP_PATH_MARKER = "virtualization/virtual-machines/backups/all/create"
_LONG_RUNNING_SNAPSHOT_PATH_MARKER = (
    "virtualization/virtual-machines/snapshots/all/create"
)
_LONG_HTTP_READ_TIMEOUT = (5, 3600)


def http_timeout_for_sync_path(path: str) -> float | tuple[int, int]:
    """Return read timeout for a backend sync path (long for backup/snapshot bulk ops)."""
    if _LONG_RUNNING_BACKUP_PATH_MARKER in path:
        return _LONG_HTTP_READ_TIMEOUT
    if _LONG_RUNNING_SNAPSHOT_PATH_MARKER in path:
        return _LONG_HTTP_READ_TIMEOUT
    return 5


def sse_error_frames(
    message: str, *, final_message: str = "Stream request failed."
) -> Generator[str, None, None]:
    """Yield SSE error and complete events for stream consumers."""
    yield "event: error\n"
    yield f"data: {json.dumps({'step': 'stream', 'status': 'failed', 'error': message})}\n\n"
    yield "event: complete\n"
    yield f"data: {json.dumps({'ok': False, 'message': final_message})}\n\n"


def get_fastapi_request_context() -> BackendRequestContext | None:
    """Build auth headers and URLs for the first configured FastAPI endpoint, if any."""
    fastapi_service_obj = FastAPIEndpoint.objects.first()
    if fastapi_service_obj is None:
        return None

    raw: dict[str, Any] = get_fastapi_url(fastapi_service_obj) or {}
    if not isinstance(raw, dict):
        raw = {}
    return {
        "detail": raw,
        "http_url": raw.get("http_url"),
        "ip_address_url": raw.get("ip_address_url"),
        "verify_ssl": bool(raw.get("verify_ssl", True)),
        "headers": get_backend_auth_headers(fastapi_service_obj),
    }


def request_backend_resource(
    context: BackendRequestContext,
    path: str,
    query_params: dict | None = None,
    *,
    timeout: float | tuple[int, int] = 5,
) -> tuple[dict, int]:
    """GET a JSON resource from the backend, trying primary URL then IP fallback."""
    http_url = context.get("http_url")
    if not http_url:
        return {
            "queued": False,
            "path": path,
            "requested_urls": [],
            "detail": "No FastAPI URL found.",
        }, 503

    fastapi_path = f"{http_url}/{path}"
    requested_urls: list[str] = []
    backend_headers = context.get("headers") or {}
    last_detail = None

    verify_ssl = bool(context.get("verify_ssl", True))
    request_candidates = [(fastapi_path, verify_ssl)]
    fallback_url = context.get("ip_address_url")
    if fallback_url:
        fallback_path = f"{fallback_url}/{path}"
        if fallback_path != fastapi_path:
            request_candidates.append((fallback_path, verify_ssl))

    for url, verify in request_candidates:
        try:
            requested_urls.append(url)
            response = requests.get(
                url,
                params=query_params,
                headers=backend_headers,
                verify=verify,
                timeout=timeout,
            )
            response.raise_for_status()
            payload = response.json() if hasattr(response, "json") else {}
            return {
                "queued": True,
                "path": path,
                "requested_urls": requested_urls,
                "response": payload,
            }, 202
        except requests.exceptions.RequestException as exc:
            last_detail, _ = extract_backend_error_detail(exc)
            logger.error("Sync request failed for %s via %s: %s", path, url, exc)
            if getattr(exc, "response", None) is not None:
                break
        except Exception as exc:  # pragma: no cover
            last_detail = str(exc)
            logger.error("Unexpected sync error for %s via %s: %s", path, url, exc)

    return {
        "queued": False,
        "path": path,
        "requested_urls": requested_urls,
        "detail": last_detail or "Unable to reach the ProxBox backend.",
    }, 503


def iter_backend_sse_lines(
    context: BackendRequestContext,
    path: str,
    query_params: dict | None = None,
) -> Generator[str, None, None]:
    """Stream newline-terminated SSE lines from the backend, with URL fallback."""
    try:
        backend_headers = context.get("headers") or {}
        http_url = context.get("http_url")
        if not http_url:
            yield from sse_error_frames("No FastAPI URL found.")
            return

        verify_ssl = bool(context.get("verify_ssl", True))
        request_candidates = [
            (f"{http_url}/{path}", verify_ssl),
        ]
        fallback_url = context.get("ip_address_url")
        if fallback_url:
            fallback_path = f"{fallback_url}/{path}"
            if fallback_path != request_candidates[0][0]:
                request_candidates.append((fallback_path, verify_ssl))

        last_error = None
        for url, verify in request_candidates:
            try:
                with requests.get(
                    url,
                    params=query_params,
                    headers=backend_headers,
                    verify=verify,
                    timeout=(5, 3600),
                    stream=True,
                ) as response:
                    response.raise_for_status()
                    for raw_line in response.iter_lines(decode_unicode=True):
                        if raw_line is None:
                            continue
                        line = str(raw_line)
                        yield f"{line}\n"
                    return
            except requests.exceptions.RequestException as exc:
                detail, _ = extract_backend_error_detail(exc)
                last_error = detail
                logger.exception("Sync stream request failed for %s via %s", path, url)
                if getattr(exc, "response", None) is not None:
                    break
            except Exception as exc:  # pragma: no cover
                last_error = str(exc)
                logger.exception(
                    "Unexpected sync stream error for %s via %s", path, url
                )

        payload = last_error or "Unable to reach the ProxBox backend stream."
        yield from sse_error_frames(payload)
    except Exception as exc:  # pragma: no cover
        logger.exception("Stream proxy crashed while handling %s", path)
        yield from sse_error_frames(str(exc), final_message="Stream proxy failed.")


def sync_resource(path: str, query_params: dict | None = None) -> tuple[dict, int]:
    """Queue a single backend sync path (GET) using the default FastAPI endpoint."""
    context = get_fastapi_request_context()
    if context is None or not context.get("http_url"):
        return {"queued": False, "detail": "No FastAPI URL found."}, 404

    return request_backend_resource(
        context,
        path,
        query_params=query_params,
        timeout=http_timeout_for_sync_path(path),
    )


def sync_full_update_resource(query_params: dict | None = None) -> tuple[dict, int]:
    """Run devices, VMs, then backups stages against the backend in sequence."""
    context = get_fastapi_request_context()
    if context is None or not context.get("http_url"):
        return {"queued": False, "detail": "No FastAPI URL found."}, 404

    requested_urls: list[str] = []
    steps = [
        ("devices", "dcim/devices/create"),
        ("virtual-machines", "virtualization/virtual-machines/create"),
        ("backups", "virtualization/virtual-machines/backups/all/create"),
    ]
    responses: dict[str, dict] = {}

    for stage, path in steps:
        step_params = dict(query_params or {})
        if _LONG_RUNNING_BACKUP_PATH_MARKER in path:
            step_params["delete_nonexistent_backup"] = True
        qp = step_params if step_params else None
        payload, status = request_backend_resource(
            context,
            path,
            query_params=qp,
            timeout=http_timeout_for_sync_path(path),
        )
        requested_urls.extend(payload.get("requested_urls", []))
        if status >= 400:
            return {
                "queued": False,
                "path": "full-update",
                "stage": stage,
                "requested_urls": requested_urls,
                "detail": payload.get("detail", "Unable to reach the ProxBox backend."),
            }, status
        responses[stage] = payload.get("response", {})

    return {
        "queued": True,
        "path": "full-update",
        "requested_urls": requested_urls,
        "detail": "Full update sync completed successfully.",
        "response": responses,
    }, 202
