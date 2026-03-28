from __future__ import annotations

import logging

import requests
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from netbox_proxbox.models import FastAPIEndpoint, ProxmoxEndpoint
from netbox_proxbox.utils import get_fastapi_url, get_ip_address_host


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


@require_GET
def get_proxmox_card(request, pk: int) -> JsonResponse:
    try:
        proxmox_object = ProxmoxEndpoint.objects.get(pk=pk)
    except ProxmoxEndpoint.DoesNotExist:
        return JsonResponse({"detail": "Proxmox endpoint not found."}, status=404)

    fastapi_object = FastAPIEndpoint.objects.first()
    if fastapi_object is None:
        return JsonResponse({"cluster_data": {}, "object": {"name": proxmox_object.name, "pk": proxmox_object.pk}})

    fastapi_info = get_fastapi_url(fastapi_object)
    fastapi_url = fastapi_info.get("http_url")
    if not fastapi_url:
        return JsonResponse({"cluster_data": {}, "object": {"name": proxmox_object.name, "pk": proxmox_object.pk}})

    domain = proxmox_object.domain or get_ip_address_host(proxmox_object.ip_address)
    version_endpoint = f"{fastapi_url}/proxmox/version?domain={domain}"
    cluster_endpoint = f"{fastapi_url}/proxmox/sessions?domain={domain}"

    version_data = []
    cluster_data = []
    try:
        version_response = requests.get(version_endpoint, timeout=5)
        cluster_response = requests.get(cluster_endpoint, timeout=5)
        version_response.raise_for_status()
        cluster_response.raise_for_status()
        version_data = version_response.json()
        cluster_data = cluster_response.json()
    except requests.exceptions.RequestException as exc:
        logger.error("Unable to hydrate Proxmox card for endpoint %s: %s", pk, exc)

    return JsonResponse(
        {
            "cluster_data": _merge_cluster_payloads(version_data, cluster_data),
            "object": {
                "pk": getattr(proxmox_object, "pk", getattr(proxmox_object, "id", None)),
                "name": proxmox_object.name,
                "domain": proxmox_object.domain,
                "ip_address": str(proxmox_object.ip_address) if proxmox_object.ip_address else None,
            },
        }
    )
