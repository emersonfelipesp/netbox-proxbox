"""Reachability checks for FastAPI, NetBox, and Proxmox via the ProxBox backend."""

from __future__ import annotations

import logging
import time

import requests

from netbox_proxbox.models import FastAPIEndpoint, NetBoxEndpoint, ProxmoxEndpoint
from netbox_proxbox.schemas.service_status import (
    FastAPIStatusResult,
    ServiceCheckResult,
)
from netbox_proxbox.utils import (
    get_backend_auth_headers,
    get_fastapi_url,
    get_ip_address_host,
)
from netbox_proxbox.views.backend_sync import sync_proxmox_endpoint_to_backend
from netbox_proxbox.views.error_utils import (
    extract_backend_error_detail,
    extract_proxmox_backend_error_detail,
    parse_requests_response_json,
)

logger = logging.getLogger(__name__)


def _fetch_backend_endpoints(
    netbox_endpoint_url: str,
    auth_headers: dict[str, str],
    timeout: float,
) -> tuple[list | None, str | None]:
    """Fetch existing endpoints from the backend. Returns (data, error)."""
    try:
        response = requests.get(
            netbox_endpoint_url,
            headers=auth_headers,
            timeout=timeout,
        )
        response.raise_for_status()
        endpoints_data, json_err = parse_requests_response_json(
            response, log_label="netbox/endpoint"
        )
        if json_err:
            return None, json_err
        if not isinstance(endpoints_data, list):
            return None, "Expected list of endpoints from backend"
        return endpoints_data, None
    except requests.exceptions.RequestException as exc:
        detail, _ = extract_backend_error_detail(exc)
        return None, detail


def _create_netbox_endpoint(
    netbox_endpoint_url: str,
    current_netbox: dict[str, object],
    auth_headers: dict[str, str],
    timeout: float,
) -> bool:
    """Create a new NetBox endpoint in the backend."""
    try:
        create_resp = requests.post(
            netbox_endpoint_url,
            json=current_netbox,
            headers=auth_headers,
            timeout=timeout,
        )
        create_resp.raise_for_status()
        return True
    except requests.exceptions.RequestException as exc:
        detail, _ = extract_backend_error_detail(exc)
        logger.error("Failed to create NetBox endpoint: %s", detail)
        return False


def _update_netbox_endpoint(
    netbox_endpoint_url: str,
    target_id: int,
    updated_data: dict[str, object],
    auth_headers: dict[str, str],
    timeout: float,
) -> bool:
    """Update an existing NetBox endpoint in the backend."""
    try:
        update_resp = requests.put(
            f"{netbox_endpoint_url}/{target_id}",
            json=updated_data,
            headers=auth_headers,
            timeout=timeout,
        )
        update_resp.raise_for_status()
        return True
    except requests.exceptions.RequestException as exc:
        detail, _ = extract_backend_error_detail(exc)
        logger.error("Failed to update NetBox endpoint: %s", detail)
        return False


def _delete_stale_endpoints(
    netbox_endpoint_url: str,
    endpoints_data: list,
    keep_target_id: int,
    auth_headers: dict[str, str],
    timeout: float,
) -> None:
    """Delete endpoints that are not the target."""
    for endpoint in endpoints_data:
        endpoint_id = endpoint.get("id")
        if endpoint_id and endpoint_id != keep_target_id:
            try:
                requests.delete(
                    f"{netbox_endpoint_url}/{endpoint_id}",
                    headers=auth_headers,
                    timeout=timeout,
                )
            except requests.exceptions.RequestException as exc:
                logger.warning(
                    "Failed to delete stale endpoint %s: %s", endpoint_id, exc
                )


class ServiceStatus:
    """Probe FastAPI, NetBox, and Proxmox integration through the configured backend."""

    request_timeout = 5
    backend_status_timeout = 60

    def __init__(self) -> None:
        """Initialize mutable state used while probing the ProxBox backend."""
        self.connected_url: str | None = None
        self.connected_verify_ssl: bool = True
        self.last_error_detail: str | None = None
        self.last_error_http_status: int | None = None

    def _set_error(self, detail: str | None, http_status: int | None = None) -> None:
        """Record the last error message and optional HTTP status for API responses."""
        self.last_error_detail = detail
        self.last_error_http_status = http_status

    def _clear_error(self) -> None:
        """Clear recorded error state before a new check."""
        self.last_error_detail = None
        self.last_error_http_status = None

    @staticmethod
    def _extract_error_detail(
        exc: requests.exceptions.RequestException,
    ) -> tuple[str, int | None]:
        """Normalize ``requests`` errors into a user-facing string and HTTP code."""
        return extract_backend_error_detail(exc)

    @staticmethod
    def backend_auth_headers(fastapi_obj: FastAPIEndpoint | None) -> dict[str, str]:
        """Return Authorization headers for backend requests."""
        return get_backend_auth_headers(fastapi_obj)

    @staticmethod
    def _compact_payload(payload: dict[str, object]) -> dict[str, object]:
        """Drop null/empty values before POST/PUT to the backend."""
        return {k: v for k, v in payload.items() if v not in (None, "")}

    @staticmethod
    def _effective_netbox_backend_credentials(
        endpoint: NetBoxEndpoint,
    ) -> dict[str, str | None]:
        """Build token_version/token/token_key payload for backend NetBox registration."""
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

    def fastapi_status(self, pk: int) -> FastAPIStatusResult:
        """Return connectivity info for the FastAPI endpoint primary key."""
        connected = False
        fastapi_url = None
        connected_verify_ssl = True
        self._clear_error()
        target_address = None
        target_port = None

        try:
            fastapi_service_obj = FastAPIEndpoint.objects.get(pk=pk)
        except FastAPIEndpoint.DoesNotExist:
            logger.warning("FastAPI endpoint with pk=%s not found", pk)
            self._set_error(f"FastAPI endpoint with id={pk} not found.")
            return FastAPIStatusResult(
                url=None,
                connected=False,
                target_address=None,
                target_port=None,
                authentication="error",
                api_access="error",
                detail=self.last_error_detail,
            )

        fastapi_detail: dict[str, object] = get_fastapi_url(fastapi_service_obj) or {}
        if not isinstance(fastapi_detail, dict):
            fastapi_detail = {}
        fastapi_url = fastapi_detail.get("http_url")
        fastapi_verify_ssl = fastapi_detail.get("verify_ssl", True)
        target_address = fastapi_detail.get("domain") or fastapi_detail.get(
            "ip_address"
        )
        if not target_address:
            target_address = "unknown"
        target_port = fastapi_service_obj.port or 8080

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
                        target_address = (
                            fastapi_detail.get("ip_address") or target_address
                        )
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

        return FastAPIStatusResult(
            url=fastapi_url,
            connected=connected,
            connected_verify_ssl=connected_verify_ssl,
            target_address=target_address if connected else None,
            target_port=target_port if connected else None,
            authentication="success" if connected else "error",
            api_access="success" if connected else "error",
            detail=self.last_error_detail,
            http_status=self.last_error_http_status,
        )

    def _build_netbox_payload(
        self,
        netbox_service_obj: NetBoxEndpoint,
        ip_address: str,
        domain: str,
    ) -> dict[str, object] | None:
        """Build compact NetBox endpoint payload for backend sync."""
        credentials = self._effective_netbox_backend_credentials(netbox_service_obj)
        payload: dict[str, object] = {
            "id": netbox_service_obj.pk,
            "name": netbox_service_obj.name or None,
            "ip_address": ip_address,
            "domain": domain,
            "port": netbox_service_obj.port or None,
            "token": credentials.get("token"),
            "token_version": credentials.get("token_version"),
            "token_key": credentials.get("token_key"),
            "verify_ssl": bool(netbox_service_obj.verify_ssl),
        }
        return self._compact_payload(payload)

    def _validate_netbox_payload(
        self,
        payload: dict[str, object],
        target_address: str,
        target_port: int,
    ) -> ServiceCheckResult | None:
        """Validate NetBox credentials and return error result if invalid."""
        token_version = payload.get("token_version")
        if token_version == "v1" and not payload.get("token"):
            self._set_error(
                "NetBox v1 token is missing. Select a v1 token with a retrievable plaintext value, or switch to v2 key/secret credentials."
            )
            return ServiceCheckResult(
                target_address=target_address,
                target_port=target_port,
                authentication="error",
                api_access="error",
                detail=self.last_error_detail,
            )
        if token_version == "v2" and (
            not payload.get("token") or not payload.get("token_key")
        ):
            self._set_error(
                "NetBox v2 credentials are incomplete. Provide both token key and token secret."
            )
            return ServiceCheckResult(
                target_address=target_address,
                target_port=target_port,
                authentication="error",
                api_access="error",
                detail=self.last_error_detail,
            )
        return None

    def _sync_netbox_to_backend(
        self,
        base_url: str,
        current_netbox: dict[str, object],
        auth_headers: dict[str, str],
    ) -> bool:
        """Sync NetBox endpoint to backend (create/update/delete stale). Returns success."""
        netbox_endpoint_url = f"{base_url}/netbox/endpoint"
        max_retries = 3
        retry_delay = 1

        for attempt in range(max_retries):
            endpoints_data, fetch_err = _fetch_backend_endpoints(
                netbox_endpoint_url, auth_headers, self.request_timeout
            )
            if fetch_err:
                logger.error(
                    "NetBox sync attempt %s failed: %s", attempt + 1, fetch_err
                )
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                continue

            if not endpoints_data:
                if _create_netbox_endpoint(
                    netbox_endpoint_url,
                    current_netbox,
                    auth_headers,
                    self.request_timeout,
                ):
                    time.sleep(retry_delay)
                    return True
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                continue

            target = next(
                (
                    ep
                    for ep in endpoints_data
                    if ep.get("id") == current_netbox.get("id")
                ),
                endpoints_data[0],
            )
            target_id = target["id"]
            updated = target | current_netbox
            updated["id"] = target_id

            if not _update_netbox_endpoint(
                netbox_endpoint_url,
                target_id,
                updated,
                auth_headers,
                self.request_timeout,
            ):
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                continue

            _delete_stale_endpoints(
                netbox_endpoint_url,
                endpoints_data,
                target_id,
                auth_headers,
                self.request_timeout,
            )
            return True

        return False

    def _check_netbox_backend_status(
        self,
        base_url: str,
        auth_headers: dict[str, str],
    ) -> bool:
        """Check if backend can reach NetBox. Returns success."""
        netbox_status_route = f"{base_url}/netbox/status"
        max_retries = 3
        retry_delay = 1

        for attempt in range(max_retries):
            try:
                response = requests.get(
                    netbox_status_route,
                    headers=auth_headers,
                    timeout=self.backend_status_timeout,
                )
                response.raise_for_status()
                return True
            except requests.exceptions.RequestException as exc:
                detail, http_status = self._extract_error_detail(exc)
                self._set_error(
                    f"NetBox backend status check failed: {detail}",
                    http_status=http_status,
                )
                logger.error(
                    "NetBox status check attempt %s failed: %s", attempt + 1, exc
                )
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
        return False

    def netbox_status(
        self,
        pk: int,
        base_url: str,
        auth_headers: dict[str, str] | None = None,
    ) -> tuple[str, ServiceCheckResult]:
        """Validate NetBox endpoint settings without re-entering NetBox via the backend."""
        status = "error"
        self._clear_error()

        try:
            netbox_service_obj = NetBoxEndpoint.objects.get(pk=pk)
        except NetBoxEndpoint.DoesNotExist:
            logger.error("NetBox endpoint with pk=%s not found", pk)
            self._set_error(f"NetBox endpoint with id={pk} not found.")
            return status, ServiceCheckResult(
                target_address=None,
                target_port=None,
                authentication="error",
                api_access="error",
                detail=self.last_error_detail,
            )

        ip_address = get_ip_address_host(
            getattr(netbox_service_obj, "ip_address", None)
        )
        domain = (netbox_service_obj.domain or "").strip() or ip_address
        target_address = domain
        target_port = netbox_service_obj.port or 443

        current_netbox = self._build_netbox_payload(
            netbox_service_obj, ip_address, domain
        )
        if current_netbox is None:
            return status, ServiceCheckResult(
                target_address=target_address,
                target_port=target_port,
                authentication="error",
                api_access="error",
                detail="Failed to build NetBox payload",
            )

        validation_error = self._validate_netbox_payload(
            current_netbox, target_address, target_port
        )
        if validation_error:
            return status, validation_error

        # NetBox keepalive runs inside the NetBox request cycle. Calling the
        # backend's `/netbox/status` route from here re-enters NetBox through
        # proxbox-api and can deadlock a simple health probe.
        _ = (base_url, auth_headers)
        self._clear_error()
        status = "success"

        return status, ServiceCheckResult(
            target_address=target_address,
            target_port=target_port,
            authentication=status if status == "success" else "error",
            api_access=status,
            detail=self.last_error_detail,
        )

    def proxmox_status(
        self,
        pk: int,
        base_url: str,
        auth_headers: dict[str, str] | None = None,
        backend_verify_ssl: bool = True,
    ) -> tuple[str, ServiceCheckResult]:
        """Push Proxmox endpoint to the backend and verify version endpoint."""
        status = "error"
        max_retries = 3
        retry_delay = 1
        self._clear_error()
        target_address = None
        target_port = None
        authentication = "error"
        api_access = "error"

        request_headers = auth_headers or {}

        try:
            proxmox_service_obj = ProxmoxEndpoint.objects.get(pk=pk)
        except ProxmoxEndpoint.DoesNotExist:
            logger.error("Proxmox endpoint with pk=%s not found", pk)
            self._set_error(f"Proxmox endpoint with id={pk} not found.")
            return status, ServiceCheckResult(
                target_address=None,
                target_port=None,
                authentication="error",
                api_access="error",
                detail=self.last_error_detail,
            )

        proxmox_ip_address = get_ip_address_host(
            getattr(proxmox_service_obj, "ip_address", None)
        )
        proxmox_domain = proxmox_service_obj.domain or None
        proxmox_host = proxmox_domain or proxmox_ip_address
        target_address = proxmox_host
        target_port = proxmox_service_obj.port or 8006

        sync_ok, sync_detail, sync_http_status = sync_proxmox_endpoint_to_backend(
            proxmox_service_obj,
            base_url=base_url,
            auth_headers=request_headers,
            backend_verify_ssl=backend_verify_ssl,
            timeout=self.request_timeout,
        )
        if not sync_ok:
            self._set_error(sync_detail, http_status=sync_http_status)
            return status, ServiceCheckResult(
                target_address=target_address,
                target_port=target_port,
                authentication="error",
                api_access="error",
                detail=self.last_error_detail,
            )
        authentication = "success"

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

        api_access = status
        return status, ServiceCheckResult(
            target_address=target_address,
            target_port=target_port,
            authentication=authentication,
            api_access=api_access,
            detail=self.last_error_detail,
        )
