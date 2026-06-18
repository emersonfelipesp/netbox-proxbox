"""Reachability checks for FastAPI, NetBox, and Proxmox via the ProxBox backend."""

from __future__ import annotations

import logging
import time
from typing import Any

import requests

from netbox_proxbox.models import FastAPIEndpoint, NetBoxEndpoint, ProxmoxEndpoint
from netbox_proxbox.schemas.service_status import (
    FastAPIStatusResult,
    ServiceCheckResult,
)
from netbox_proxbox.services.backend_version import backend_version_advisories
from netbox_proxbox.services.endpoint_enabled import disabled_endpoint_detail
from netbox_proxbox.utils import (
    get_backend_auth_headers,
    get_fastapi_url,
    get_ip_address_host,
)
from netbox_proxbox.views.error_utils import (
    extract_backend_error_detail,
    extract_proxmox_backend_error_detail,
    parse_requests_response_json,
)

logger = logging.getLogger(__name__)

# Module-level throttle for the keepalive NetBox endpoint push.
# Prevents spamming the backend on every dashboard keepalive poll.
_last_netbox_endpoint_push: float = 0.0
_NETBOX_PUSH_THROTTLE_SECONDS: float = 300.0  # 5 minutes

# Per-endpoint throttle for the keepalive Proxmox mode detection.
_last_proxmox_mode_check: dict[int, float] = {}
_PROXMOX_MODE_CHECK_THROTTLE_SECONDS: float = 300.0  # 5 minutes


def _maybe_push_netbox_endpoints_to_backend(
    base_url: str,
    auth_headers: dict[str, str],
    backend_verify_ssl: bool,
) -> None:
    """Push NetBox endpoint data to the backend if the throttle window has elapsed.

    Best-effort: logs warnings on failure but never raises.
    Called after ``fastapi_status()`` confirms the backend is reachable so the
    backend always has a current ``NetBoxEndpoint`` record — even after a fresh
    start or database wipe — without requiring user interaction.
    """
    global _last_netbox_endpoint_push

    now = time.monotonic()
    if now - _last_netbox_endpoint_push < _NETBOX_PUSH_THROTTLE_SECONDS:
        return

    try:
        from netbox_proxbox.models import NetBoxEndpoint as _NB  # noqa: PLC0415
        from netbox_proxbox.services.backend_auth import (  # noqa: PLC0415
            ensure_backend_key_registered,
        )
        from netbox_proxbox.views.backend_sync import (  # noqa: PLC0415
            sync_netbox_endpoint_to_backend as _push,
        )

        endpoints = list(_NB.objects.filter(enabled=True))
        if not endpoints:
            logger.debug(
                "Keepalive push: no enabled NetBoxEndpoint configured, skipping"
            )
            _last_netbox_endpoint_push = now
            return

        # Ensure the API key is registered before making authenticated requests.
        # This is the path that recovers when the backend restarts with a fresh
        # database — the keepalive check fires first, then the push follows.
        key_ok, key_msg = ensure_backend_key_registered()
        if key_ok:
            logger.info("Keepalive push: API key verified — %s", key_msg)
        else:
            logger.warning("Keepalive push: API key registration failed — %s", key_msg)

        for nb_ep in endpoints:
            ok, err, _ = _push(
                nb_ep,
                base_url=base_url,
                auth_headers=auth_headers,
                backend_verify_ssl=backend_verify_ssl,
            )
            if ok:
                logger.info(
                    "Keepalive push: synced NetBox endpoint '%s' to proxbox-api backend",
                    getattr(nb_ep, "name", nb_ep.pk),
                )
            else:
                logger.warning(
                    "Keepalive push: could not sync NetBox endpoint '%s' to proxbox-api: %s",
                    getattr(nb_ep, "name", nb_ep.pk),
                    err,
                )

        _last_netbox_endpoint_push = now

    except Exception:  # noqa: BLE001
        logger.warning(
            "Keepalive push: failed to push NetBox endpoints to proxbox-api backend",
            exc_info=True,
        )


def sync_proxmox_endpoint_to_backend(
    endpoint: ProxmoxEndpoint,
    *,
    base_url: str,
    auth_headers: dict[str, str] | None = None,
    backend_verify_ssl: bool = True,
    timeout: int = 15,
) -> tuple[bool, str | None, int | None]:
    """Compatibility wrapper for callers that patch this service module symbol."""
    from netbox_proxbox.views.backend_sync import (
        sync_proxmox_endpoint_to_backend as _sync,
    )

    return _sync(
        endpoint,
        base_url=base_url,
        auth_headers=auth_headers,
        backend_verify_ssl=backend_verify_ssl,
        timeout=timeout,
    )


def resolve_backend_endpoint_id(
    endpoint: ProxmoxEndpoint,
    *,
    base_url: str,
    auth_headers: dict[str, str] | None = None,
    backend_verify_ssl: bool = True,
    timeout: int = 15,
) -> tuple[int | None, str | None]:
    """Compatibility wrapper for callers that patch this service module symbol."""
    from netbox_proxbox.views.backend_sync import (  # noqa: PLC0415
        resolve_backend_endpoint_id as _resolve,
    )

    return _resolve(
        endpoint,
        base_url=base_url,
        auth_headers=auth_headers,
        backend_verify_ssl=backend_verify_ssl,
        timeout=timeout,
    )


def _maybe_update_proxmox_endpoint_mode(
    endpoint: ProxmoxEndpoint,
    base_url: str,
    auth_headers: dict[str, str],
    query_params: dict[str, str],
    backend_verify_ssl: bool,
) -> None:
    """Detect standalone-vs-cluster topology and persist it on the endpoint.

    Best-effort: logs debug on failure but never raises.
    Throttled per endpoint pk (once per 5 minutes) so it adds no measurable
    overhead to the keepalive dashboard poll.
    """
    global _last_proxmox_mode_check

    try:
        pk = getattr(endpoint, "pk", getattr(endpoint, "id", None))
        if pk is None:
            return

        now = time.monotonic()
        if (
            now - _last_proxmox_mode_check.get(pk, float("-inf"))
            < _PROXMOX_MODE_CHECK_THROTTLE_SECONDS
        ):
            return

        from netbox_proxbox.schemas import ProxmoxClusterStatusResponse  # noqa: PLC0415

        resp = requests.get(
            f"{base_url}/proxmox/cluster/status",
            params=query_params,
            headers=auth_headers,
            verify=backend_verify_ssl,
            timeout=10,
        )
        resp.raise_for_status()
        cluster_data = ProxmoxClusterStatusResponse.model_validate(resp.json())

        cluster_record = cluster_data.cluster_record
        node_records = cluster_data.node_records

        if cluster_record and len(node_records) > 1:
            mode = "cluster"
        elif len(node_records) == 1:
            mode = "standalone"
        else:
            mode = "undefined"

        current_mode = getattr(endpoint, "mode", None)
        if current_mode != mode:
            endpoint.mode = mode
            if callable(getattr(endpoint, "save", None)):
                endpoint.save(update_fields=["mode"])
            logger.info(
                "Keepalive mode update: endpoint '%s' (pk=%s) mode set to %s",
                getattr(endpoint, "name", pk),
                pk,
                mode,
            )

        _last_proxmox_mode_check[pk] = now

    except Exception:  # noqa: BLE001
        logger.debug(
            "Keepalive mode update: failed to detect mode for endpoint pk=%s",
            getattr(endpoint, "pk", getattr(endpoint, "id", "?")),
            exc_info=True,
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

    def _probe_backend_version(
        self,
        *,
        base_url: str,
        fastapi_obj: FastAPIEndpoint,
        verify_ssl: bool,
    ) -> tuple[str | None, list[str], str | None]:
        """Fetch proxbox-api version and return (version, warnings, blocking_error)."""
        version_url = f"{base_url.rstrip('/')}/version"
        try:
            response = requests.get(
                version_url,
                headers=self.backend_auth_headers(fastapi_obj),
                verify=verify_ssl,
                timeout=self.request_timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.exceptions.RequestException as exc:
            detail, _ = self._extract_error_detail(exc)
            return (
                None,
                [
                    (
                        "ProxBox backend is reachable, but its version could not be "
                        f"verified at {version_url}: {detail}"
                    )
                ],
                None,
            )
        except ValueError:
            return (
                None,
                [
                    (
                        "ProxBox backend is reachable, but its /version endpoint "
                        "returned a non-JSON response."
                    )
                ],
                None,
            )

        version = None
        if isinstance(payload, dict):
            raw_version = payload.get("version")
            if raw_version not in (None, ""):
                version = str(raw_version)

        if not version:
            return (
                None,
                [
                    (
                        "ProxBox backend is reachable, but its /version response did "
                        "not include a version string."
                    )
                ],
                None,
            )

        advisories = backend_version_advisories(version)
        warning_messages = [
            advisory.message
            for advisory in advisories
            if advisory.severity == "warning"
        ]
        blocking_error = next(
            (
                advisory.message
                for advisory in advisories
                if advisory.severity == "error"
            ),
            None,
        )
        return version, warning_messages, blocking_error

    def fastapi_status(self, pk: int) -> FastAPIStatusResult:
        """Return connectivity info for the FastAPI endpoint primary key."""
        connected = False
        fastapi_url = None
        connected_verify_ssl = True
        self._clear_error()
        target_address = None
        target_port = None
        backend_version = None
        warnings: list[str] = []

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

        disabled_detail = disabled_endpoint_detail(
            fastapi_service_obj,
            kind="FastAPI endpoint",
            action="skipping status check",
        )
        if disabled_detail:
            logger.info("Skipping FastAPI status check for disabled endpoint %s", pk)
            self._set_error(disabled_detail)
            return FastAPIStatusResult(
                url=None,
                connected=False,
                target_address=get_ip_address_host(
                    getattr(fastapi_service_obj, "ip_address", None)
                )
                or (getattr(fastapi_service_obj, "domain", None) or None),
                target_port=getattr(fastapi_service_obj, "port", None) or 8080,
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
            except requests.exceptions.SSLError as exc:
                detail, http_status = self._extract_error_detail(exc)
                if fastapi_verify_ssl:
                    self._set_error(
                        f"FastAPI URL check failed: {detail}",
                        http_status=http_status,
                    )
                    logger.error(
                        "SSL error connecting to FastAPI at %s with verify_ssl=True: %s",
                        fastapi_url,
                        exc,
                    )
                else:
                    ip_url = fastapi_detail.get("ip_address_url")
                    if ip_url:
                        try:
                            # Intentional fallback to IP URL after SSL hostname
                            # failure; the endpoint operator already opted into
                            # verify=False at config time on the FastAPIEndpoint.
                            response = requests.get(
                                ip_url,
                                verify=False,  # nosec B501
                                timeout=self.request_timeout,
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

        # After a successful connectivity check, push NetBox endpoint data to the
        # backend.  This ensures the backend always has the endpoint record even
        # after a fresh start or DB wipe, covering the gap between plugin restarts
        # and the post_save signal.  The push is throttled to at most once per 5
        # minutes so it does not spam the backend on every keepalive poll.
        if connected and self.connected_url:
            _maybe_push_netbox_endpoints_to_backend(
                base_url=self.connected_url.rstrip("/"),
                auth_headers=self.backend_auth_headers(fastapi_service_obj),
                backend_verify_ssl=connected_verify_ssl,
            )
            backend_version, warnings, blocking_error = self._probe_backend_version(
                base_url=self.connected_url,
                fastapi_obj=fastapi_service_obj,
                verify_ssl=connected_verify_ssl,
            )
            if blocking_error:
                self._set_error(blocking_error)

        return FastAPIStatusResult(
            url=fastapi_url,
            backend_version=backend_version,
            connected=connected,
            connected_verify_ssl=connected_verify_ssl,
            target_address=target_address if connected else None,
            target_port=target_port if connected else None,
            authentication="success" if connected else "error",
            api_access=(
                "success" if connected and self.last_error_detail is None else "error"
            ),
            detail=self.last_error_detail,
            http_status=self.last_error_http_status,
            warnings=warnings,
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

        disabled_detail = disabled_endpoint_detail(
            netbox_service_obj,
            kind="NetBox endpoint",
            action="skipping status check",
        )
        if disabled_detail:
            logger.info("Skipping NetBox status check for disabled endpoint %s", pk)
            self._set_error(disabled_detail)
            return status, ServiceCheckResult(
                target_address=target_address,
                target_port=target_port,
                authentication="error",
                api_access="error",
                detail=self.last_error_detail,
            )

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

        if not bool(getattr(proxmox_service_obj, "enabled", True)):
            logger.info("Skipping Proxmox status check for disabled endpoint %s", pk)
            self._set_error("Proxmox endpoint is disabled; skipping status check.")
            return "disabled", ServiceCheckResult(
                target_address=get_ip_address_host(
                    getattr(proxmox_service_obj, "ip_address", None)
                )
                or (getattr(proxmox_service_obj, "domain", None) or None),
                target_port=getattr(proxmox_service_obj, "port", None) or 8006,
                authentication="disabled",
                api_access="disabled",
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
        backend_endpoint_id, resolve_error = resolve_backend_endpoint_id(
            proxmox_service_obj,
            base_url=base_url,
            auth_headers=request_headers,
            backend_verify_ssl=backend_verify_ssl,
            timeout=self.request_timeout,
        )
        if backend_endpoint_id is None:
            self._set_error(
                resolve_error
                or "Failed to resolve Proxmox endpoint on ProxBox backend."
            )
            return status, ServiceCheckResult(
                target_address=target_address,
                target_port=target_port,
                authentication=authentication,
                api_access="error",
                detail=self.last_error_detail,
            )
        query_params = {
            "source": "database",
            "proxmox_endpoint_ids": str(backend_endpoint_id),
        }

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

        if status == "success":
            _maybe_update_proxmox_endpoint_mode(
                endpoint=proxmox_service_obj,
                base_url=base_url,
                auth_headers=request_headers,
                query_params=query_params,
                backend_verify_ssl=backend_verify_ssl,
            )

        api_access = status
        return status, ServiceCheckResult(
            target_address=target_address,
            target_port=target_port,
            authentication=authentication,
            api_access=api_access,
            detail=self.last_error_detail,
        )

    @staticmethod
    def _pbs_status_item_value(item: object, key: str) -> object:
        if isinstance(item, dict):
            return item.get(key)
        return getattr(item, key, None)

    @classmethod
    def _match_pbs_status_item(
        cls,
        *,
        items: list[object],
        endpoint_id: int | None,
        host: str,
        port: int,
        name: str,
    ) -> object | None:
        for item in items:
            if cls._pbs_status_item_value(item, "endpoint_id") == endpoint_id:
                return item

        for item in items:
            item_host = str(cls._pbs_status_item_value(item, "host") or "")
            item_port = cls._pbs_status_item_value(item, "port")
            if item_host == host and item_port == port:
                return item

        for item in items:
            if str(cls._pbs_status_item_value(item, "name") or "") == name:
                return item

        return None

    def pbs_status(
        self,
        endpoint: object,
        base_url: str,
        auth_headers: dict[str, str] | None = None,
        backend_verify_ssl: bool = True,
    ) -> tuple[str, ServiceCheckResult]:
        """Fetch proxbox-api PBS reachability and normalize it for a home badge."""
        status = "error"
        self._clear_error()

        endpoint_id = getattr(endpoint, "pk", getattr(endpoint, "id", None))
        name = str(getattr(endpoint, "name", "") or endpoint)
        host = str(
            getattr(endpoint, "host", "")
            or getattr(endpoint, "domain", "")
            or get_ip_address_host(getattr(endpoint, "ip_address", None))
        )
        port = int(getattr(endpoint, "port", 8007) or 8007)
        request_headers = auth_headers or {}
        url = f"{base_url.rstrip('/')}/pbs/status"

        disabled_detail = disabled_endpoint_detail(
            endpoint, kind="PBS endpoint", action="skipping status check"
        )
        if disabled_detail:
            logger.info(
                "Skipping PBS status check for disabled endpoint %s", endpoint_id
            )
            self._set_error(disabled_detail)
            return status, ServiceCheckResult(
                target_address=host,
                target_port=port,
                authentication="error",
                api_access="error",
                detail=self.last_error_detail,
            )

        try:
            response = requests.get(
                url,
                headers=request_headers,
                verify=backend_verify_ssl,
                timeout=self.request_timeout,
            )
            response.raise_for_status()
            payload, json_err = parse_requests_response_json(
                response, log_label="pbs/status"
            )
        except requests.exceptions.RequestException as exc:
            detail, http_status = self._extract_error_detail(exc)
            self._set_error(
                f"Failed to check PBS status through ProxBox backend: {detail}",
                http_status=http_status,
            )
            return status, ServiceCheckResult(
                target_address=host,
                target_port=port,
                authentication="error",
                api_access="error",
                detail=self.last_error_detail,
                http_status=self.last_error_http_status,
            )

        if json_err:
            self._set_error(json_err)
            return status, ServiceCheckResult(
                target_address=host,
                target_port=port,
                authentication="success",
                api_access="error",
                detail=self.last_error_detail,
            )

        items: list[Any] = []
        if isinstance(payload, dict) and isinstance(payload.get("items"), list):
            items = payload["items"]
        else:
            self._set_error("ProxBox backend returned invalid PBS status payload.")
            return status, ServiceCheckResult(
                target_address=host,
                target_port=port,
                authentication="success",
                api_access="error",
                detail=self.last_error_detail,
            )

        item = self._match_pbs_status_item(
            items=items,
            endpoint_id=endpoint_id,
            host=host,
            port=port,
            name=name,
        )
        if item is None:
            self._set_error(f"PBS status for {name} was not returned by proxbox-api.")
            return status, ServiceCheckResult(
                target_address=host,
                target_port=port,
                authentication="success",
                api_access="error",
                detail=self.last_error_detail,
            )

        if bool(self._pbs_status_item_value(item, "reachable")):
            self._clear_error()
            return "success", ServiceCheckResult(
                target_address=host,
                target_port=port,
                authentication="success",
                api_access="success",
            )

        reason = self._pbs_status_item_value(item, "reason")
        self._set_error(
            str(reason) if reason else f"PBS endpoint {name} is not reachable."
        )
        return status, ServiceCheckResult(
            target_address=host,
            target_port=port,
            authentication="success",
            api_access="error",
            detail=self.last_error_detail,
        )
