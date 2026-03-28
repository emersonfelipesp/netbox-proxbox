"""Check backend, NetBox, and Proxmox service reachability for the plugin UI."""

from __future__ import annotations

import logging
import time

import requests
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from netbox_proxbox.models import FastAPIEndpoint, NetBoxEndpoint, ProxmoxEndpoint
from netbox_proxbox.utils import (
    get_backend_auth_headers,
    get_fastapi_url,
    get_ip_address_host,
)
from netbox_proxbox.views.backend_sync import sync_proxmox_endpoint_to_backend
from netbox_proxbox.views.error_utils import (
    extract_backend_error_detail,
    extract_proxmox_backend_error_detail,
)


logger = logging.getLogger(__name__)


class ServiceStatus:
    request_timeout = 5

    def __init__(self):
        self.connected_url = None
        self.connected_verify_ssl = True
        self.last_error_detail = None
        self.last_error_http_status = None

    def _set_error(self, detail: str | None, http_status: int | None = None) -> None:
        self.last_error_detail = detail
        self.last_error_http_status = http_status

    def _clear_error(self) -> None:
        self.last_error_detail = None
        self.last_error_http_status = None

    @staticmethod
    def _extract_error_detail(
        exc: requests.exceptions.RequestException,
    ) -> tuple[str, int | None]:
        return extract_backend_error_detail(exc)

    @staticmethod
    def _backend_auth_headers(fastapi_obj: FastAPIEndpoint | None) -> dict[str, str]:
        return get_backend_auth_headers(fastapi_obj)

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
        connected_verify_ssl = True
        self._clear_error()

        try:
            fastapi_service_obj = FastAPIEndpoint.objects.get(pk=pk)
        except FastAPIEndpoint.DoesNotExist:
            logger.warning("FastAPI endpoint with pk=%s not found", pk)
            self._set_error(f"FastAPI endpoint with id={pk} not found.")
            return {"url": None, "connected": False, "detail": self.last_error_detail}

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
                self.connected_verify_ssl = fastapi_verify_ssl
                connected_verify_ssl = fastapi_verify_ssl
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
                        self.connected_verify_ssl = False
                        connected_verify_ssl = False
                    except requests.exceptions.RequestException as exc:
                        detail, http_status = self._extract_error_detail(exc)
                        self._set_error(
                            f"FastAPI fallback URL check failed: {detail}",
                            http_status=http_status,
                        )
                        logger.error(
                            "Failed to connect to FastAPI fallback URL %s: %s",
                            ip_url,
                            exc,
                        )
            except requests.exceptions.RequestException as exc:
                detail, http_status = self._extract_error_detail(exc)
                self._set_error(
                    f"FastAPI URL check failed: {detail}",
                    http_status=http_status,
                )
                logger.error("Error connecting to FastAPI at %s: %s", fastapi_url, exc)

        return {
            "url": fastapi_url,
            "connected": connected,
            "connected_verify_ssl": connected_verify_ssl,
            "detail": self.last_error_detail,
            "http_status": self.last_error_http_status,
        }

    def netbox_status(
        self,
        pk: int,
        base_url: str,
        auth_headers: dict[str, str] | None = None,
    ) -> str:
        status = "error"
        max_retries = 3
        retry_delay = 1
        self._clear_error()

        request_headers = auth_headers or {}

        try:
            netbox_service_obj = NetBoxEndpoint.objects.get(pk=pk)
        except NetBoxEndpoint.DoesNotExist:
            logger.error("NetBox endpoint with pk=%s not found", pk)
            self._set_error(f"NetBox endpoint with id={pk} not found.")
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

        token_version = current_netbox.get("token_version")
        if token_version == "v1" and not current_netbox.get("token"):
            self._set_error(
                "NetBox v1 token is missing. Select a v1 token with a retrievable plaintext value, or switch to v2 key/secret credentials."
            )
            return status
        if token_version == "v2" and (
            not current_netbox.get("token") or not current_netbox.get("token_key")
        ):
            self._set_error(
                "NetBox v2 credentials are incomplete. Provide both token key and token secret."
            )
            return status

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
                self._clear_error()
                status = "success"
                break
            except requests.exceptions.RequestException as exc:
                detail, http_status = self._extract_error_detail(exc)
                self._set_error(detail, http_status=http_status)
                response = getattr(exc, "response", None)
                if response is not None:
                    response_text = getattr(response, "text", "") or ""
                    response_body = response_text[:500]
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

    def proxmox_status(
        self,
        pk: int,
        base_url: str,
        auth_headers: dict[str, str] | None = None,
        backend_verify_ssl: bool = True,
    ) -> str:
        status = "error"
        max_retries = 3
        retry_delay = 1
        self._clear_error()

        request_headers = auth_headers or {}

        try:
            proxmox_service_obj = ProxmoxEndpoint.objects.get(pk=pk)
        except ProxmoxEndpoint.DoesNotExist:
            logger.error("Proxmox endpoint with pk=%s not found", pk)
            self._set_error(f"Proxmox endpoint with id={pk} not found.")
            return status

        proxmox_ip_address = get_ip_address_host(
            getattr(proxmox_service_obj, "ip_address", None)
        )
        proxmox_domain = proxmox_service_obj.domain or None
        proxmox_host = proxmox_domain or proxmox_ip_address

        sync_ok, sync_detail, sync_http_status = sync_proxmox_endpoint_to_backend(
            proxmox_service_obj,
            base_url=base_url,
            auth_headers=request_headers,
            backend_verify_ssl=backend_verify_ssl,
            timeout=self.request_timeout,
        )
        if not sync_ok:
            self._set_error(sync_detail, http_status=sync_http_status)
            return status

        url = f"{base_url}/proxmox/version"
        query_params = {"source": "database"}
        if proxmox_domain:
            query_params["domain"] = proxmox_domain
        else:
            query_params["ip_address"] = proxmox_ip_address

        for attempt in range(max_retries):
            try:
                response = requests.get(
                    url,
                    params=query_params,
                    headers=request_headers,
                    verify=backend_verify_ssl,
                    timeout=self.request_timeout,
                )
                response.raise_for_status()
                self._clear_error()
                status = "success"
                break
            except requests.exceptions.RequestException as exc:
                detail, http_status = extract_proxmox_backend_error_detail(
                    exc,
                    proxmox_host=proxmox_host,
                    proxmox_port=proxmox_service_obj.port,
                    backend_url=url,
                )
                self._set_error(detail, http_status=http_status)
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
        payload: dict = {"status": status}
        if fastapi_response.get("detail"):
            payload["detail"] = fastapi_response["detail"]
        return JsonResponse(payload)

    fastapi_object = FastAPIEndpoint.objects.first()
    if fastapi_object is None:
        logger.error("No FastAPI endpoints found")
        return JsonResponse(
            {
                "status": "error",
                "detail": "No FastAPI endpoint is configured.",
            },
            status=503,
        )

    fastapi_response = service_status.fastapi_status(pk=fastapi_object.id)
    if not fastapi_response.get("connected"):
        return JsonResponse(
            {
                "status": "error",
                "detail": fastapi_response.get("detail")
                or "Unable to connect to configured FastAPI endpoint.",
            },
            status=503,
        )

    auth_headers = service_status._backend_auth_headers(fastapi_object)

    if not service_status.connected_url:
        logger.error(
            "FastAPI connectivity reported success but no connected URL was recorded"
        )
        return JsonResponse(
            {
                "status": "error",
                "detail": "FastAPI endpoint responded, but no connected URL was recorded.",
            },
            status=503,
        )

    connected_url = service_status.connected_url

    if service == "netbox":
        status = service_status.netbox_status(
            pk=pk,
            base_url=connected_url,
            auth_headers=auth_headers,
        )
    elif service == "proxmox":
        status = service_status.proxmox_status(
            pk=pk,
            base_url=connected_url,
            auth_headers=auth_headers,
            backend_verify_ssl=service_status.connected_verify_ssl,
        )

    payload: dict = {"status": status}
    if status != "success" and service_status.last_error_detail:
        payload["detail"] = service_status.last_error_detail
    if status != "success" and service_status.last_error_http_status is not None:
        payload["http_status"] = service_status.last_error_http_status

    return JsonResponse(payload)
