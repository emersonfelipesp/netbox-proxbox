"""Build dashboard card payloads from Proxmox and backend API responses."""

from __future__ import annotations

import logging

import requests
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from netbox_proxbox.models import FastAPIEndpoint, ProxmoxEndpoint
from netbox_proxbox.utils import get_fastapi_url, get_ip_address_host
from netbox_proxbox.views.backend_sync import sync_proxmox_endpoint_to_backend
from netbox_proxbox.views.error_utils import extract_proxmox_backend_error_detail


logger = logging.getLogger(__name__)


def _merge_cluster_payloads(version_payload, cluster_payload) -> dict:
    version_data = {}
    cluster_data = {}

    if version_payload:
        for _, value in version_payload[0].items():
            version_data = value
            break

    if cluster_payload:
        cluster_data = cluster_payload[0]

    if isinstance(cluster_data, dict) and isinstance(version_data, dict):
        return cluster_data | version_data
    return {}


def _backend_auth_headers(fastapi_obj: FastAPIEndpoint | None) -> dict[str, str]:
    token = (getattr(fastapi_obj, "token", "") or "").strip()
    if not token:
        return {}

    if token.startswith("Bearer ") or token.startswith("Token "):
        return {"Authorization": token}

    return {"Authorization": f"Bearer {token}"}


@require_GET
def get_proxmox_card(request, pk: int) -> JsonResponse:
    try:
        proxmox_object = ProxmoxEndpoint.objects.get(pk=pk)
    except ProxmoxEndpoint.DoesNotExist:
        return JsonResponse({"detail": "Proxmox endpoint not found."}, status=404)

    fastapi_object = FastAPIEndpoint.objects.first()
    if fastapi_object is None:
        return JsonResponse(
            {
                "cluster_data": {},
                "object": {"name": proxmox_object.name, "pk": proxmox_object.pk},
            }
        )

    fastapi_info = get_fastapi_url(fastapi_object) or {}
    if not isinstance(fastapi_info, dict):
        fastapi_info = {}
    fastapi_url = fastapi_info.get("http_url")
    if not fastapi_url:
        return JsonResponse(
            {
                "cluster_data": {},
                "detail": "No FastAPI backend URL is configured.",
                "object": {"name": proxmox_object.name, "pk": proxmox_object.pk},
            }
        )

    backend_headers = _backend_auth_headers(fastapi_object)
    backend_verify_ssl = bool(fastapi_info.get("verify_ssl", True))

    domain = (proxmox_object.domain or "").strip()
    ip_address = get_ip_address_host(proxmox_object.ip_address)
    proxmox_host = domain or ip_address
    query_params = {"source": "database"}
    if domain:
        query_params["domain"] = domain
    else:
        query_params["ip_address"] = ip_address

    version_endpoint = f"{fastapi_url}/proxmox/version"
    cluster_endpoint = f"{fastapi_url}/proxmox/sessions"

    version_data = []
    cluster_data = []
    detail = None
    http_status = None

    sync_ok, sync_detail, sync_http_status = sync_proxmox_endpoint_to_backend(
        proxmox_object,
        base_url=fastapi_url,
        auth_headers=backend_headers,
        backend_verify_ssl=backend_verify_ssl,
        timeout=5,
    )
    if not sync_ok:
        payload = {
            "cluster_data": {},
            "object": {
                "pk": getattr(
                    proxmox_object, "pk", getattr(proxmox_object, "id", None)
                ),
                "name": proxmox_object.name,
                "domain": proxmox_object.domain,
                "ip_address": str(proxmox_object.ip_address)
                if proxmox_object.ip_address
                else None,
            },
            "detail": sync_detail,
        }
        if sync_http_status is not None:
            payload["http_status"] = sync_http_status
        return JsonResponse(payload)

    try:
        version_response = requests.get(
            version_endpoint,
            params=query_params,
            headers=backend_headers,
            verify=backend_verify_ssl,
            timeout=5,
        )
        cluster_response = requests.get(
            cluster_endpoint,
            params=query_params,
            headers=backend_headers,
            verify=backend_verify_ssl,
            timeout=5,
        )
        version_response.raise_for_status()
        cluster_response.raise_for_status()
        version_data = version_response.json()
        cluster_data = cluster_response.json()
    except requests.exceptions.RequestException as exc:
        failed_endpoint = version_endpoint
        response = getattr(exc, "response", None)
        if response is not None:
            response_url = getattr(response, "url", "") or ""
            if "/proxmox/sessions" in response_url:
                failed_endpoint = cluster_endpoint
            elif "/proxmox/version" in response_url:
                failed_endpoint = version_endpoint
        elif "/proxmox/sessions" in str(exc):
            failed_endpoint = cluster_endpoint
        detail, http_status = extract_proxmox_backend_error_detail(
            exc,
            proxmox_host=proxmox_host,
            proxmox_port=proxmox_object.port,
            backend_url=failed_endpoint,
        )
        logger.error("Unable to hydrate Proxmox card for endpoint %s: %s", pk, exc)

    payload: dict = {
        "cluster_data": _merge_cluster_payloads(version_data, cluster_data),
        "object": {
            "pk": getattr(proxmox_object, "pk", getattr(proxmox_object, "id", None)),
            "name": proxmox_object.name,
            "domain": proxmox_object.domain,
            "ip_address": str(proxmox_object.ip_address)
            if proxmox_object.ip_address
            else None,
        },
    }
    if detail:
        payload["detail"] = detail
    if http_status is not None:
        payload["http_status"] = http_status

    return JsonResponse(payload)
