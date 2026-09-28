"""Backend authentication, key registration, and readiness helpers."""

from __future__ import annotations

import logging
import time as time_module

import requests

from netbox_proxbox.models import FastAPIEndpoint
from netbox_proxbox.schemas.backend_proxy import BackendRequestContext
from netbox_proxbox.views.error_utils import (
    extract_backend_error_detail,
    redact_sensitive_text,
)

logger = logging.getLogger(__name__)

_LONG_RUNNING_VM_SYNC_MARKER = "virtualization/virtual-machines"
_LONG_RUNNING_FULL_UPDATE_MARKER = "full-update"
_LONG_HTTP_READ_TIMEOUT = (5, 3600)

# Bounded readiness wait used by the sync preflight.  Deliberately much shorter
# than the ``wait_for_backend_ready`` defaults (30 retries, up to 30s apart):
# the preflight only needs to absorb a cold start, and a backend that is truly
# down should surface that quickly rather than stalling the job for minutes.
PREFLIGHT_READY_MAX_RETRIES = 5
PREFLIGHT_READY_INITIAL_DELAY = 1.0
PREFLIGHT_READY_MAX_DELAY = 8.0


def _remaining_budget(time_budget: float | None, started: float) -> float | None:
    """Return the current remaining readiness budget when one was supplied."""
    if time_budget is None:
        return None
    return max(time_budget - (time_module.monotonic() - started), 0.0)


def _health_response_result(response: requests.Response) -> tuple[bool, str] | None:
    """Classify terminal readiness responses and leave retryable ones open."""
    if 300 <= response.status_code < 400:
        return False, "Backend redirects are not permitted."
    if response.status_code != 200:
        return None
    try:
        init_status = response.json().get("status", "unknown")
    except Exception:
        init_status = "unknown"
    if init_status != "ready":
        logger.info(
            "Backend reachable but status=%s (init may be incomplete); "
            "proceeding — SSE endpoint will report errors if needed",
            init_status,
        )
    return True, "Backend is reachable"


def http_timeout_for_sync_path(path: str) -> float | tuple[int, int]:
    """Return read timeout for a backend sync path (long for bulk/full-update ops).

    VMs with 50+ interfaces require extended time to sync all interfaces, IPs, and VLANs.
    Full-update runs all sync stages sequentially, potentially taking 30+ minutes for
    large Proxmox clusters. Use 1-hour read timeout for these operations.

    Note: The VM marker subsumes backup and snapshot paths (they all contain
    'virtualization/virtual-machines'), so only the broader markers need to be checked.
    """
    if _LONG_RUNNING_VM_SYNC_MARKER in path:
        return _LONG_HTTP_READ_TIMEOUT
    if _LONG_RUNNING_FULL_UPDATE_MARKER in path:
        return _LONG_HTTP_READ_TIMEOUT
    return 5


def _try_register_key(
    context: BackendRequestContext,
    token: str,
    *,
    failure_details: dict[str, object] | None = None,
    timeout: float | None = None,
) -> tuple[bool, str]:
    """Authenticate a stored API key without changing backend state.

    Returns (success, message) tuple.
    """
    from netbox_proxbox.services.backend_key_adoption import (
        BackendKeyAdoptionError,
        adopt_backend_key_at_url,
    )

    if not context or not context.http_url:
        return False, "No FastAPI URL configured"

    base_url = context.http_url.rstrip("/")
    verify_ssl = bool(context.verify_ssl)

    try:
        adopt_backend_key_at_url(
            base_url,
            verify_ssl,
            token,
            label="netbox-proxbox-plugin",
            timeout=timeout,
        )
    except BackendKeyAdoptionError as exc:
        if failure_details is not None:
            failure_details.update(
                code=exc.code,
                status_code=exc.status_code,
                retry_after=exc.retry_after,
            )
        return False, f"Backend key check failed ({exc.code})"
    return True, "Key authenticated successfully"


def _try_register_key_fallback() -> tuple[bool, str]:
    """Try authenticating keys from enabled FastAPIEndpoints with fallback.

    Iterates through all endpoints and attempts to register each token.
    Returns (success, message) tuple showing the last attempt result.
    """
    from netbox_proxbox.utils import get_fastapi_context

    endpoints = FastAPIEndpoint.objects.filter(enabled=True).order_by("pk")
    if not endpoints:
        return False, "No enabled FastAPI endpoints configured"

    last_message = "No keys attempted"
    for endpoint in endpoints:
        token = (getattr(endpoint, "token", "") or "").strip()
        if not token:
            last_message = f"Endpoint {endpoint.pk} has no token, skipping"
            logger.debug(last_message)
            continue

        context = get_fastapi_context(endpoint)
        if not context:
            last_message = f"Endpoint {endpoint.pk} has no context, skipping"
            logger.debug(last_message)
            continue

        success, message = _try_register_key(
            BackendRequestContext(
                detail=context,
                endpoint_id=context.get("endpoint_id"),
                target_fingerprint=str(context.get("target_fingerprint", "")),
                http_url=context.get("http_url"),
                ip_address_url=context.get("ip_address_url"),
                verify_ssl=context.get("verify_ssl", True),
                headers=context.get("headers", {}),
            ),
            token,
        )
        if success:
            return True, f"Authenticated endpoint {endpoint.pk}: {message}"
        last_message = f"Endpoint {endpoint.pk} failed: {message}"
        logger.warning(
            "Token authentication failed for endpoint %s: %s", endpoint.pk, message
        )

    return False, last_message


def wait_for_backend_ready(
    context: BackendRequestContext,
    max_retries: int = 30,
    initial_delay: float = 1.0,
    max_delay: float = 30.0,
    time_budget: float | None = None,
) -> tuple[bool, str]:
    """Wait for the FastAPI backend to be ready before starting sync.

    Returns:
        tuple of (success, message)
    """
    if not context or not context.http_url:
        return False, "No FastAPI URL configured"

    backend_url = context.http_url.rstrip("/")
    health_url = f"{backend_url}/health"
    verify_ssl = bool(context.verify_ssl)
    headers = context.headers or {}

    started = time_module.monotonic()
    delay = initial_delay
    for attempt in range(max_retries):
        remaining = _remaining_budget(time_budget, started)
        if remaining is not None and remaining <= 0:
            return False, "Job deadline reached while checking backend readiness."
        try:
            response = requests.get(
                health_url,
                headers=headers,
                verify=verify_ssl,
                timeout=min(5, remaining) if remaining is not None else 5,
                allow_redirects=False,
            )
            result = _health_response_result(response)
            if result is not None:
                return result

            if attempt < max_retries - 1:
                logger.info(
                    "Backend health check failed with HTTP %s (attempt %s/%s), retrying in %ss",
                    response.status_code,
                    attempt + 1,
                    max_retries,
                    delay,
                )
                remaining = _remaining_budget(time_budget, started)
                sleep_for = min(delay, remaining) if remaining is not None else delay
                time_module.sleep(sleep_for)
                delay = min(delay * 1.5, max_delay)
                continue
        except requests.exceptions.RequestException as exc:
            if attempt < max_retries - 1:
                logger.info(
                    "Backend health check request failed (attempt %s/%s): %s, retrying in %ss",
                    attempt + 1,
                    max_retries,
                    f"{type(exc).__name__}: {redact_sensitive_text(str(exc))}"[:160],
                    delay,
                )
                remaining = _remaining_budget(time_budget, started)
                sleep_for = min(delay, remaining) if remaining is not None else delay
                time_module.sleep(sleep_for)
                delay = min(delay * 1.5, max_delay)
                continue

    return False, f"Backend not reachable after {max_retries} attempts"


def ensure_backend_key_registered(
    endpoint_id: int | None = None,
    *,
    failure_details: dict[str, object] | None = None,
    timeout: float | None = None,
) -> tuple[bool, str]:
    """Check whether the stored API key authenticates with the backend.

    The historical public name is retained for compatibility. This helper is
    deliberately read-only and never calls the unauthenticated bootstrap POST.

    Returns (success, message) tuple.
    """
    from netbox_proxbox.services.backend_context import get_fastapi_endpoint_with_token

    endpoint, context = get_fastapi_endpoint_with_token(endpoint_id=endpoint_id)
    if endpoint is None:
        return False, "No FastAPI endpoint configured"

    if context is None or not context.http_url:
        return False, "No FastAPI URL configured"

    return authenticate_backend_request_context(
        context,
        failure_details=failure_details,
        timeout=timeout,
    )


def authenticate_backend_request_context(
    context: BackendRequestContext,
    *,
    failure_details: dict[str, object] | None = None,
    timeout: float | None = None,
) -> tuple[bool, str]:
    """Authenticate the exact URL/key pair captured in one request context."""
    token = (context.headers or {}).get("X-Proxbox-API-Key", "").strip()
    if not token:
        return False, "No API token configured on FastAPI endpoint"
    return _try_register_key(
        context, token, failure_details=failure_details, timeout=timeout
    )
