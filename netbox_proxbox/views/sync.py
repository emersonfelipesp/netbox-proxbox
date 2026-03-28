"""Trigger sync operations on the external ProxBox backend over HTTP."""

from __future__ import annotations

import logging

import requests
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from netbox_proxbox.models import FastAPIEndpoint
from netbox_proxbox.utils import get_fastapi_url


logger = logging.getLogger(__name__)


def _get_fastapi_request_context():
    fastapi_service_obj = FastAPIEndpoint.objects.first()
    if fastapi_service_obj is None:
        return None

    fastapi_detail = get_fastapi_url(fastapi_service_obj)
    return {
        "detail": fastapi_detail,
        "http_url": fastapi_detail.get("http_url"),
        "verify_ssl": fastapi_detail.get("verify_ssl", True),
    }


def sync_resource(path: str, query_params: dict | None = None) -> tuple[dict, int]:
    context = _get_fastapi_request_context()
    if context is None or not context["http_url"]:
        return {"queued": False, "detail": "No FastAPI URL found."}, 404

    fastapi_path = f"{context['http_url']}/{path}"
    requested_urls = []

    for url, verify in (
        (fastapi_path, context["verify_ssl"]),
        (f"{context['detail']['ip_address_url']}/{path}", False),
    ):
        try:
            requested_urls.append(url)
            response = requests.get(url, params=query_params, verify=verify, timeout=5)
            response.raise_for_status()
            payload = response.json() if hasattr(response, "json") else {}
            return {
                "queued": True,
                "path": path,
                "requested_urls": requested_urls,
                "response": payload,
            }, 202
        except requests.exceptions.RequestException as exc:
            logger.error("Sync request failed for %s via %s: %s", path, url, exc)
        except Exception as exc:  # pragma: no cover
            logger.error("Unexpected sync error for %s via %s: %s", path, url, exc)

    return {
        "queued": False,
        "path": path,
        "requested_urls": requested_urls,
        "detail": "Unable to reach the ProxBox backend.",
    }, 503


@require_GET
def sync_devices(request) -> JsonResponse:
    payload, status = sync_resource("dcim/devices/create")
    return JsonResponse(payload, status=status)


@require_GET
def sync_virtual_machines(request) -> JsonResponse:
    payload, status = sync_resource("virtualization/virtual-machines/create")
    return JsonResponse(payload, status=status)


@require_GET
def sync_full_update(request) -> JsonResponse:
    payload, status = sync_resource("full-update")
    return JsonResponse(payload, status=status)


@require_GET
def sync_vm_backups(request) -> JsonResponse:
    payload, status = sync_resource(
        "virtualization/virtual-machines/backups/all/create",
        query_params={"delete_nonexistent_backup": True},
    )
    return JsonResponse(payload, status=status)
