"""Trigger sync operations on the external ProxBox backend over HTTP."""

from __future__ import annotations

import logging
import json
from collections.abc import Generator

import requests
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.http import StreamingHttpResponse
from django.shortcuts import redirect
from django.views.decorators.http import require_http_methods

from netbox_proxbox.models import FastAPIEndpoint
from netbox_proxbox.utils import get_backend_auth_headers, get_fastapi_url
from netbox_proxbox.views.error_utils import extract_backend_error_detail


logger = logging.getLogger(__name__)

# proxbox-api awaits the full backup sync in one GET; allow long read like the stream proxy.
_LONG_RUNNING_BACKUP_PATH_MARKER = "virtualization/virtual-machines/backups/all/create"
_LONG_HTTP_READ_TIMEOUT = (5, 3600)


def _http_timeout_for_sync_path(path: str) -> float | tuple[int, int]:
    if _LONG_RUNNING_BACKUP_PATH_MARKER in path:
        return _LONG_HTTP_READ_TIMEOUT
    return 5


def _sse_error_frames(message: str, *, final_message: str = "Stream request failed."):
    yield "event: error\n"
    yield f"data: {json.dumps({'step': 'stream', 'status': 'failed', 'error': message})}\n\n"
    yield "event: complete\n"
    yield f"data: {json.dumps({'ok': False, 'message': final_message})}\n\n"


def _wants_json_response(request) -> bool:
    if request is None:
        return True

    requested_with = ""
    headers = getattr(request, "headers", {}) or {}
    if isinstance(headers, dict):
        requested_with = headers.get("X-Requested-With", "")
        accept = headers.get("Accept", "")
    else:
        requested_with = getattr(headers, "get", lambda *args, **kwargs: "")(
            "X-Requested-With", ""
        )
        accept = getattr(headers, "get", lambda *args, **kwargs: "")("Accept", "")

    return requested_with == "XMLHttpRequest" or "application/json" in accept


def _get_fastapi_request_context():
    fastapi_service_obj = FastAPIEndpoint.objects.first()
    if fastapi_service_obj is None:
        return None

    fastapi_detail = get_fastapi_url(fastapi_service_obj) or {}
    if not isinstance(fastapi_detail, dict):
        fastapi_detail = {}
    return {
        "detail": fastapi_detail,
        "http_url": fastapi_detail.get("http_url"),
        "ip_address_url": fastapi_detail.get("ip_address_url"),
        "verify_ssl": fastapi_detail.get("verify_ssl", True),
        "headers": get_backend_auth_headers(fastapi_service_obj),
    }


def _request_backend_resource(
    context: dict,
    path: str,
    query_params: dict | None = None,
    *,
    timeout: float | tuple[int, int] = 5,
) -> tuple[dict, int]:
    fastapi_path = f"{context['http_url']}/{path}"
    requested_urls = []
    backend_headers = context.get("headers") or {}
    last_detail = None

    request_candidates = [(fastapi_path, context["verify_ssl"])]
    fallback_url = context.get("ip_address_url")
    if fallback_url:
        fallback_path = f"{fallback_url}/{path}"
        if fallback_path != fastapi_path:
            request_candidates.append((fallback_path, context["verify_ssl"]))

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


def _iter_backend_sse_lines(
    context: dict,
    path: str,
    query_params: dict | None = None,
) -> Generator[str, None, None]:
    try:
        backend_headers = context.get("headers") or {}
        http_url = context.get("http_url")
        if not http_url:
            yield from _sse_error_frames("No FastAPI URL found.")
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
        yield from _sse_error_frames(payload)
    except Exception as exc:  # pragma: no cover
        logger.exception("Stream proxy crashed while handling %s", path)
        yield from _sse_error_frames(str(exc), final_message="Stream proxy failed.")


def sync_resource(path: str, query_params: dict | None = None) -> tuple[dict, int]:
    context = _get_fastapi_request_context()
    if context is None or not context["http_url"]:
        return {"queued": False, "detail": "No FastAPI URL found."}, 404

    return _request_backend_resource(
        context,
        path,
        query_params=query_params,
        timeout=_http_timeout_for_sync_path(path),
    )


def sync_full_update_resource(query_params: dict | None = None) -> tuple[dict, int]:
    context = _get_fastapi_request_context()
    if context is None or not context["http_url"]:
        return {"queued": False, "detail": "No FastAPI URL found."}, 404

    requested_urls = []
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
        payload, status = _request_backend_resource(
            context,
            path,
            query_params=qp,
            timeout=_http_timeout_for_sync_path(path),
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


def _sync_response(
    request, *, path: str, action_label: str, query_params: dict | None = None
):
    if path == "full-update":
        merged_qp = {**(query_params or {})}
        if request is not None and getattr(request, "GET", None):
            merged_qp.update(dict(request.GET.items()))
        payload, status = sync_full_update_resource(
            query_params=merged_qp if merged_qp else None
        )
    else:
        payload, status = sync_resource(path, query_params=query_params)
    if _wants_json_response(request):
        return JsonResponse(payload, status=status)

    detail = payload.get("detail")
    if status < 400:
        messages.success(request, detail or f"{action_label} sync queued successfully.")
    else:
        messages.error(request, detail or f"{action_label} sync failed.")
    return redirect("plugins:netbox_proxbox:home")


def _sync_stream_response(
    request,
    *,
    path: str,
    query_params: dict | None = None,
):
    try:
        context = _get_fastapi_request_context()
        if context is None:
            stream_iter = _sse_error_frames("No FastAPI endpoint configured.")
        else:
            stream_path = f"{path.rstrip('/')}/stream"
            stream_iter = _iter_backend_sse_lines(
                context,
                stream_path,
                query_params=query_params,
            )

        response = StreamingHttpResponse(
            stream_iter,
            content_type="text/event-stream",
        )
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response
    except Exception as exc:  # pragma: no cover
        logger.exception("Failed to build stream response for %s", path)
        response = StreamingHttpResponse(
            _sse_error_frames(
                str(exc), final_message="Stream response bootstrap failed."
            ),
            content_type="text/event-stream",
        )
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response


@login_required
@require_http_methods(["GET", "POST"])
def sync_devices(request):
    return _sync_response(
        request,
        path="dcim/devices/create",
        action_label="Devices",
    )


@login_required
@require_http_methods(["GET", "POST"])
def sync_virtual_machines(request):
    return _sync_response(
        request,
        path="virtualization/virtual-machines/create",
        action_label="Virtual machines",
    )


@login_required
@require_http_methods(["GET", "POST"])
def sync_full_update(request):
    return _sync_response(
        request,
        path="full-update",
        action_label="Full update",
    )


@login_required
@require_http_methods(["GET", "POST"])
def sync_vm_backups(request):
    return _sync_response(
        request,
        path="virtualization/virtual-machines/backups/all/create",
        action_label="VM backups",
        query_params={"delete_nonexistent_backup": True},
    )


@login_required
@require_http_methods(["GET"])
def sync_vm_backups_stream(request):
    return _sync_stream_response(
        request,
        path="virtualization/virtual-machines/backups/all/create",
        query_params={"delete_nonexistent_backup": True},
    )


@login_required
@require_http_methods(["GET"])
def sync_devices_stream(request):
    return _sync_stream_response(
        request,
        path="dcim/devices/create",
    )


@login_required
@require_http_methods(["GET"])
def sync_virtual_machines_stream(request):
    return _sync_stream_response(
        request,
        path="virtualization/virtual-machines/create",
    )


@login_required
@require_http_methods(["GET"])
def sync_full_update_stream(request):
    return _sync_stream_response(
        request,
        path="full-update",
    )
