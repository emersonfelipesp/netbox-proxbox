"""Trigger sync operations on the external ProxBox backend over HTTP."""

from __future__ import annotations

import logging

import requests
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect
from django.views.decorators.http import require_http_methods

from netbox_proxbox.models import FastAPIEndpoint
from netbox_proxbox.utils import get_backend_auth_headers, get_fastapi_url
from netbox_proxbox.views.error_utils import extract_backend_error_detail


logger = logging.getLogger(__name__)


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


def sync_resource(path: str, query_params: dict | None = None) -> tuple[dict, int]:
    context = _get_fastapi_request_context()
    if context is None or not context["http_url"]:
        return {"queued": False, "detail": "No FastAPI URL found."}, 404

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
                timeout=5,
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
        except Exception as exc:  # pragma: no cover
            last_detail = str(exc)
            logger.error("Unexpected sync error for %s via %s: %s", path, url, exc)

    return {
        "queued": False,
        "path": path,
        "requested_urls": requested_urls,
        "detail": last_detail or "Unable to reach the ProxBox backend.",
    }, 503


def _sync_response(request, *, path: str, action_label: str, query_params: dict | None = None):
    payload, status = sync_resource(path, query_params=query_params)
    if _wants_json_response(request):
        return JsonResponse(payload, status=status)

    detail = payload.get("detail")
    if status < 400:
        messages.success(request, detail or f"{action_label} sync queued successfully.")
    else:
        messages.error(request, detail or f"{action_label} sync failed.")
    return redirect("plugins:netbox_proxbox:home")


@require_http_methods(["GET", "POST"])
def sync_devices(request):
    return _sync_response(
        request,
        path="dcim/devices/create",
        action_label="Devices",
    )


@require_http_methods(["GET", "POST"])
def sync_virtual_machines(request):
    return _sync_response(
        request,
        path="virtualization/virtual-machines/create",
        action_label="Virtual machines",
    )


@require_http_methods(["GET", "POST"])
def sync_full_update(request):
    return _sync_response(
        request,
        path="full-update",
        action_label="Full update",
    )


@require_http_methods(["GET", "POST"])
def sync_vm_backups(request):
    return _sync_response(
        request,
        path="virtualization/virtual-machines/backups/all/create",
        action_label="VM backups",
        query_params={"delete_nonexistent_backup": True},
    )
