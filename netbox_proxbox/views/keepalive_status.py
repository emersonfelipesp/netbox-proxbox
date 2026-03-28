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

    @staticmethod
    def _backend_auth_headers(fastapi_obj: FastAPIEndpoint | None) -> dict[str, str]:
        token = (getattr(fastapi_obj, "token", "") or "").strip()
        if not token:
            return {}

        if token.startswith("Bearer ") or token.startswith("Token "):
            return {"Authorization": token}

        return {"Authorization": f"Bearer {token}"}

    @staticmethod
    def _compact_payload(payload: dict) -> dict:
        return {key: value for key, value in payload.items() if value not in (None, "")}

    @staticmethod
    def _effective_netbox_backend_credentials(
        endpoint: NetBoxEndpoint,
    ) -> dict[str, str | None]:
        token_version = (
            (getattr(endpoint, "effective_token_version", "") or "v1").strip().lower()
        )
        token_value = getattr(endpoint, "effective_token_value", None)
        token_key = (getattr(endpoint, "token_key", "") or "").strip() or None
        token_secret = (getattr(endpoint, "token_secret", "") or "").strip() or None

        if token_version == "v2":
            if (
                not token_secret
                and token_value
                and token_value.startswith("nbt_")
                and "." in token_value
            ):
                token_secret = token_value.split(".", 1)[1]
            return {
                "token_version": "v2",
                "token": token_secret,
                "token_key": token_key,
            }

        return {
            "token_version": "v1",
            "token": token_value,
            "token_key": None,
        }

    def fastapi_status(self, pk: int) -> dict:
        connected = False
        fastapi_url = None

        try:
            fastapi_service_obj = FastAPIEndpoint.objects.get(pk=pk)
        except FastAPIEndpoint.DoesNotExist:
            logger.warning("FastAPI endpoint with pk=%s not found", pk)
            return {"url": None, "connected": False}

        fastapi_detail = get_fastapi_url(fastapi_service_obj) or {}
        if not isinstance(fastapi_detail, dict):
            fastapi_detail = {}
        fastapi_url = fastapi_detail.get("http_url")
        fastapi_verify_ssl = fastapi_detail.get("verify_ssl", True)

        if fastapi_url:
            try:
                response = requests.get(
                    fastapi_url, verify=fastapi_verify_ssl, timeout=self.request_timeout
                )
                response.raise_for_status()
                connected = True
                self.connected_url = fastapi_url
            except requests.exceptions.SSLError:
                ip_url = fastapi_detail.get("ip_address_url")
                if ip_url:
                    try:
                        response = requests.get(
                            ip_url, verify=False, timeout=self.request_timeout
                        )
                        response.raise_for_status()
                        connected = True
                        self.connected_url = ip_url
                    except requests.exceptions.RequestException as exc:
                        logger.error(
                            "Failed to connect to FastAPI fallback URL %s: %s",
                            ip_url,
                            exc,
                        )
            except requests.exceptions.RequestException as exc:
                logger.error("Error connecting to FastAPI at %s: %s", fastapi_url, exc)

        return {"url": fastapi_url, "connected": connected}

    def netbox_status(
        self,
        pk: int,
        base_url: str,
        auth_headers: dict[str, str] | None = None,
    ) -> str:
        status = "error"
        max_retries = 3
        retry_delay = 1

        request_headers = auth_headers or {}

        try:
            netbox_service_obj = NetBoxEndpoint.objects.get(pk=pk)
        except NetBoxEndpoint.DoesNotExist:
            logger.error("NetBox endpoint with pk=%s not found", pk)
            return status

        ip_address = get_ip_address_host(
            getattr(netbox_service_obj, "ip_address", None)
        )
        domain = (netbox_service_obj.domain or "").strip() or ip_address
        credentials = self._effective_netbox_backend_credentials(netbox_service_obj)

        current_netbox = {
            "id": pk,
            "name": netbox_service_obj.name or None,
            "ip_address": ip_address,
            "domain": domain,
            "port": netbox_service_obj.port or None,
            "token": credentials.get("token"),
            "token_version": credentials.get("token_version"),
            "token_key": credentials.get("token_key"),
            "verify_ssl": bool(netbox_service_obj.verify_ssl),
        }
        current_netbox = self._compact_payload(current_netbox)

        netbox_endpoint_url = f"{base_url}/netbox/endpoint"
        netbox_status_route = f"{base_url}/netbox/status"

        for attempt in range(max_retries):
            try:
                response = requests.get(
                    netbox_endpoint_url,
                    headers=request_headers,
                    timeout=self.request_timeout,
                )
                response.raise_for_status()
                endpoints = list(response.json())

                if not endpoints:
                    create_response = requests.post(
                        netbox_endpoint_url,
                        json=current_netbox,
                        headers=request_headers,
                        timeout=self.request_timeout,
                    )
                    create_response.raise_for_status()
                    time.sleep(retry_delay)
                else:
                    target = next(
                        (ep for ep in endpoints if ep.get("id") == pk), endpoints[0]
                    )
                    target_id = target["id"]
                    updated_endpoint = target | current_netbox
                    updated_endpoint["id"] = target_id

                    update_response = requests.put(
                        f"{netbox_endpoint_url}/{target_id}",
                        json=updated_endpoint,
                        headers=request_headers,
                        timeout=self.request_timeout,
                    )
                    update_response.raise_for_status()

                    for endpoint in endpoints:
                        endpoint_id = endpoint.get("id")
                        if endpoint_id and endpoint_id != target_id:
                            delete_response = requests.delete(
                                f"{netbox_endpoint_url}/{endpoint_id}",
                                headers=request_headers,
                                timeout=self.request_timeout,
                            )
                            delete_response.raise_for_status()

                status_response = requests.get(
                    netbox_status_route,
                    headers=request_headers,
                    timeout=self.request_timeout,
                )
                status_response.raise_for_status()
                status = "success"
                break
            except requests.exceptions.RequestException as exc:
                response = getattr(exc, "response", None)
                if response is not None:
                    response_body = response.text[:500]
                    logger.error(
                        "NetBox status request failed on attempt %s with HTTP %s: %s",
                        attempt + 1,
                        response.status_code,
                        response_body,
                    )
                logger.error(
                    "NetBox status request failed on attempt %s: %s", attempt + 1, exc
                )
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

        proxmox_ip_address = get_ip_address_host(
            getattr(proxmox_service_obj, "ip_address", None)
        )
        proxmox_domain = proxmox_service_obj.domain or None

        if proxmox_domain:
            url = f"{base_url}/proxmox/version?domain={proxmox_domain}"
        else:
            url = f"{base_url}/proxmox/version?ip_address={proxmox_ip_address}"

        for attempt in range(max_retries):
            try:
                response = requests.get(
                    url,
                    verify=proxmox_service_obj.verify_ssl,
                    timeout=self.request_timeout,
                )
                response.raise_for_status()
                status = "success"
                break
            except requests.exceptions.RequestException as exc:
                logger.error(
                    "Proxmox status request failed on attempt %s: %s", attempt + 1, exc
                )
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

    auth_headers = service_status._backend_auth_headers(fastapi_object)

    if not service_status.connected_url:
        logger.error(
            "FastAPI connectivity reported success but no connected URL was recorded"
        )
        return JsonResponse({"status": "error"}, status=503)

    connected_url = service_status.connected_url

    if service == "netbox":
        status = service_status.netbox_status(
            pk=pk,
            base_url=connected_url,
            auth_headers=auth_headers,
        )
    elif service == "proxmox":
        status = service_status.proxmox_status(pk=pk, base_url=connected_url)

    return JsonResponse({"status": status})
