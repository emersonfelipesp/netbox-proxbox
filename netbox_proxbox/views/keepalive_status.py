"""Check backend, NetBox, and Proxmox service reachability for the plugin UI."""

from __future__ import annotations

import logging
import time

import requests
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from netbox_proxbox.models import FastAPIEndpoint, NetBoxEndpoint, ProxmoxEndpoint
from netbox_proxbox.utils import get_fastapi_url, get_ip_address_host


logger = logging.getLogger(__name__)


class ServiceStatus:
    request_timeout = 5

    def __init__(self):
        self.connected_url = None

    def fastapi_status(self, pk: int) -> dict:
        connected = False
        fastapi_url = None

        try:
            fastapi_service_obj = FastAPIEndpoint.objects.get(pk=pk)
        except FastAPIEndpoint.DoesNotExist:
            logger.warning("FastAPI endpoint with pk=%s not found", pk)
            return {"url": None, "connected": False}

        fastapi_detail = get_fastapi_url(fastapi_service_obj)
        fastapi_url = fastapi_detail.get("http_url")
        fastapi_verify_ssl = fastapi_detail.get("verify_ssl", True)

        if fastapi_url:
            try:
                response = requests.get(fastapi_url, verify=fastapi_verify_ssl, timeout=self.request_timeout)
                response.raise_for_status()
                connected = True
                self.connected_url = fastapi_url
            except requests.exceptions.SSLError:
                ip_url = fastapi_detail.get("ip_address_url")
                if ip_url:
                    try:
                        response = requests.get(ip_url, verify=False, timeout=self.request_timeout)
                        response.raise_for_status()
                        connected = True
                        self.connected_url = ip_url
                    except requests.exceptions.RequestException as exc:
                        logger.error("Failed to connect to FastAPI fallback URL %s: %s", ip_url, exc)
            except requests.exceptions.RequestException as exc:
                logger.error("Error connecting to FastAPI at %s: %s", fastapi_url, exc)

        return {"url": fastapi_url, "connected": connected}

    def netbox_status(self, pk: int, base_url: str) -> str:
        status = "error"
        max_retries = 3
        retry_delay = 1

        try:
            netbox_service_obj = NetBoxEndpoint.objects.get(pk=pk)
        except NetBoxEndpoint.DoesNotExist:
            logger.error("NetBox endpoint with pk=%s not found", pk)
            return status

        current_netbox = {
            "id": pk,
            "name": netbox_service_obj.name or None,
            "ip_address": get_ip_address_host(getattr(netbox_service_obj, "ip_address", None)),
            "domain": netbox_service_obj.domain or None,
            "port": netbox_service_obj.port or None,
            "token": getattr(netbox_service_obj, "effective_token_value", None),
            "token_version": getattr(netbox_service_obj, "effective_token_version", None),
            "token_key": getattr(netbox_service_obj, "token_key", "") or None,
            "token_secret": getattr(netbox_service_obj, "token_secret", "") or None,
            "verify_ssl": bool(netbox_service_obj.verify_ssl),
        }

        netbox_endpoint_url = f"{base_url}/netbox/endpoint"
        netbox_status_route = f"{base_url}/netbox/status"

        for attempt in range(max_retries):
            try:
                response = requests.get(netbox_endpoint_url, timeout=self.request_timeout)
                response.raise_for_status()
                endpoints = list(response.json())

                if not endpoints:
                    create_response = requests.post(netbox_endpoint_url, json=current_netbox, timeout=self.request_timeout)
                    create_response.raise_for_status()
                    time.sleep(retry_delay)
                else:
                    for endpoint in endpoints:
                        if endpoint["id"] != pk:
                            requests.delete(f"{netbox_endpoint_url}/{endpoint['id']}", timeout=self.request_timeout)
                        elif endpoint != current_netbox:
                            updated_endpoint = endpoint | current_netbox
                            requests.put(
                                f"{netbox_endpoint_url}/{endpoint['id']}",
                                json=updated_endpoint,
                                timeout=self.request_timeout,
                            )

                status_response = requests.get(netbox_status_route, timeout=self.request_timeout)
                status_response.raise_for_status()
                status = "success"
                break
            except requests.exceptions.RequestException as exc:
                logger.error("NetBox status request failed on attempt %s: %s", attempt + 1, exc)
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)

        return status

    def proxmox_status(self, pk: int, base_url: str) -> str:
        status = "error"
        max_retries = 3
        retry_delay = 1

        try:
            proxmox_service_obj = ProxmoxEndpoint.objects.get(pk=pk)
        except ProxmoxEndpoint.DoesNotExist:
            logger.error("Proxmox endpoint with pk=%s not found", pk)
            return status

        proxmox_ip_address = get_ip_address_host(getattr(proxmox_service_obj, "ip_address", None))
        proxmox_domain = proxmox_service_obj.domain or None

        if proxmox_domain:
            url = f"{base_url}/proxmox/version?domain={proxmox_domain}"
        else:
            url = f"{base_url}/proxmox/version?ip_address={proxmox_ip_address}"

        for attempt in range(max_retries):
            try:
                response = requests.get(url, verify=proxmox_service_obj.verify_ssl, timeout=self.request_timeout)
                response.raise_for_status()
                status = "success"
                break
            except requests.exceptions.RequestException as exc:
                logger.error("Proxmox status request failed on attempt %s: %s", attempt + 1, exc)
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)

        return status


@require_GET
def get_service_status(request, service: str, pk: int) -> JsonResponse:
    status = "unknown"
    service_status = ServiceStatus()

    if service == "fastapi":
        fastapi_response = service_status.fastapi_status(pk)
        status = "success" if fastapi_response.get("connected") else "error"
        return JsonResponse({"status": status})

    fastapi_object = FastAPIEndpoint.objects.first()
    if fastapi_object is None:
        logger.error("No FastAPI endpoints found")
        return JsonResponse({"status": "error"}, status=503)

    fastapi_response = service_status.fastapi_status(pk=fastapi_object.id)
    if not fastapi_response.get("connected"):
        return JsonResponse({"status": "error"}, status=503)

    if service == "netbox":
        status = service_status.netbox_status(pk=pk, base_url=service_status.connected_url)
    elif service == "proxmox":
        status = service_status.proxmox_status(pk=pk, base_url=service_status.connected_url)

    return JsonResponse({"status": status})
