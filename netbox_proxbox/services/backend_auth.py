"""Backend authentication, key registration, and readiness helpers."""

from __future__ import annotations

import logging
import time as time_module

import requests

from netbox_proxbox.models import FastAPIEndpoint
from netbox_proxbox.schemas.backend_proxy import BackendRequestContext
from netbox_proxbox.views.error_utils import extract_backend_error_detail

logger = logging.getLogger(__name__)

_LONG_RUNNING_VM_SYNC_MARKER = "virtualization/virtual-machines"
_LONG_RUNNING_FULL_UPDATE_MARKER = "full-update"
_LONG_HTTP_READ_TIMEOUT = (5, 3600)

# Preflight HTTP budgets.  A freshly started proxbox-api answers its first few
# requests slowly (container start, SQLite open, NetBox OpenAPI resolution), and
# the old 5s/10s bounds failed the preflight on that start-up latency alone —
# the first sync of a new install saw bootstrap-status give up at 5.03s and the
# endpoint push at 10.02s, while a later call to the very same host answered in
# 3.78s.  These bounds leave a cold backend room to answer.  They are ceilings,
# not delays: a healthy backend still returns in well under a second.
BOOTSTRAP_STATUS_TIMEOUT = 15
REGISTER_KEY_TIMEOUT = 20

# Bounded readiness wait used by the sync preflight.  Deliberately much shorter
# than the ``wait_for_backend_ready`` defaults (30 retries, up to 30s apart):
# the preflight only needs to absorb a cold start, and a backend that is truly
# down should surface that quickly rather than stalling the job for minutes.
PREFLIGHT_READY_MAX_RETRIES = 5
PREFLIGHT_READY_INITIAL_DELAY = 1.0
PREFLIGHT_READY_MAX_DELAY = 8.0


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


def _try_register_key(context: BackendRequestContext, token: str) -> tuple[bool, str]:
    """Attempt to register the API key with the backend if not already registered.

    Returns (success, message) tuple.
    """
    import requests

    if not context or not context.http_url:
        return False, "No FastAPI URL configured"

    base_url = context.http_url.rstrip("/")
    verify_ssl = bool(context.verify_ssl)

    try:
        status_response = requests.get(
            f"{base_url}/auth/bootstrap-status",
            verify=verify_ssl,
            timeout=BOOTSTRAP_STATUS_TIMEOUT,
        )
        if status_response.status_code != 200:
            return (
                False,
                f"Bootstrap status check failed: HTTP {status_response.status_code}",
            )

        status_data = status_response.json()
        if not status_data.get("needs_bootstrap", False):
            return True, "Key already registered"

    except requests.exceptions.RequestException as exc:
        return False, f"Could not check bootstrap status: {exc}"

    try:
        register_response = requests.post(
            f"{base_url}/auth/register-key",
            json={"api_key": token, "label": "netbox-proxbox-plugin"},
            verify=verify_ssl,
            timeout=REGISTER_KEY_TIMEOUT,
        )
        if register_response.status_code == 201:
            return True, "Key registered successfully"
        if register_response.status_code == 409:
            return True, "Key already exists"
        return False, f"Registration failed: HTTP {register_response.status_code}"

    except requests.exceptions.RequestException as exc:
        return False, f"Could not register key: {exc}"


def _try_register_key_fallback() -> tuple[bool, str]:
    """Try registering keys from all FastAPIEndpoints with fallback.

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
                http_url=context.get("http_url"),
                ip_address_url=context.get("ip_address_url"),
                verify_ssl=context.get("verify_ssl", True),
                headers=context.get("headers", {}),
            ),
            token,
        )
        if success:
            return True, f"Registered endpoint {endpoint.pk}: {message}"
        last_message = f"Endpoint {endpoint.pk} failed: {message}"
        logger.warning(
            "Token registration failed for endpoint %s: %s", endpoint.pk, message
        )

    return False, last_message


def wait_for_backend_ready(
    context: BackendRequestContext,
    max_retries: int = 30,
    initial_delay: float = 1.0,
    max_delay: float = 30.0,
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

    delay = initial_delay
    for attempt in range(max_retries):
        try:
            response = requests.get(
                health_url,
                headers=headers,
                verify=verify_ssl,
                timeout=5,
            )
            if response.status_code == 200:
                # Backend is reachable — that is enough.  Whether its
                # bootstrap completed (``init_ok``) is not our concern;
                # the actual SSE endpoint will return its own error if
                # it cannot fulfil the request.
                init_status = "unknown"
                try:
                    data = response.json()
                    init_status = data.get("status", "unknown")
                except Exception:
                    pass
                if init_status != "ready":
                    logger.info(
                        "Backend reachable but status=%s (init may be incomplete); "
                        "proceeding — SSE endpoint will report errors if needed",
                        init_status,
                    )
                return True, "Backend is reachable"

            if attempt < max_retries - 1:
                logger.info(
                    "Backend health check failed with HTTP %s (attempt %s/%s), retrying in %ss",
                    response.status_code,
                    attempt + 1,
                    max_retries,
                    delay,
                )
                time_module.sleep(delay)
                delay = min(delay * 1.5, max_delay)
                continue
        except requests.exceptions.RequestException as exc:
            if attempt < max_retries - 1:
                logger.info(
                    "Backend health check request failed (attempt %s/%s): %s, retrying in %ss",
                    attempt + 1,
                    max_retries,
                    str(exc)[:100],
                    delay,
                )
                time_module.sleep(delay)
                delay = min(delay * 1.5, max_delay)
                continue

    return False, f"Backend not reachable after {max_retries} attempts"


def ensure_backend_key_registered(endpoint_id: int | None = None) -> tuple[bool, str]:
    """Check if the API key is registered with the backend, register if needed.

    Returns (success, message) tuple.
    """
    from netbox_proxbox.services.backend_context import get_fastapi_endpoint_with_token

    endpoint, context = get_fastapi_endpoint_with_token(endpoint_id=endpoint_id)
    if endpoint is None:
        return False, "No FastAPI endpoint configured"

    if context is None or not context.http_url:
        return False, "No FastAPI URL configured"

    token = (getattr(endpoint, "token", "") or "").strip()
    if not token:
        return False, "No API token configured on FastAPI endpoint"

    return _try_register_key(context, token)
