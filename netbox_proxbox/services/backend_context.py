"""Request context resolution and auth-retry helpers for backend communication."""

from __future__ import annotations

import logging

from netbox_proxbox.models import FastAPIEndpoint
from netbox_proxbox.schemas.backend_proxy import BackendRequestContext

logger = logging.getLogger(__name__)


def get_fastapi_request_context(
    endpoint_id: int | None = None,
) -> BackendRequestContext | None:
    """Build auth headers and URLs for a configured FastAPI endpoint, if any."""
    from netbox_proxbox.utils import (
        get_fastapi_context_by_id,
        get_first_fastapi_context,
    )

    context = (
        get_fastapi_context_by_id(endpoint_id)
        if endpoint_id is not None
        else get_first_fastapi_context()
    )
    if context is None:
        return None

    return BackendRequestContext(
        detail=context,
        http_url=context.get("http_url"),
        ip_address_url=context.get("ip_address_url"),
        verify_ssl=context.get("verify_ssl", True),
        headers=context.get("headers", {}),
    )


def get_fastapi_endpoint_with_token(
    endpoint_id: int | None = None,
) -> tuple[object | None, BackendRequestContext | None]:
    """Get the FastAPIEndpoint model and its request context.

    Args:
        endpoint_id: Optional specific endpoint ID. If not provided, selects by ID
            when multiple endpoints exist, or returns the only endpoint when only one exists.

    Returns (endpoint, context) tuple. Either may be None.
    """
    if endpoint_id is not None:
        endpoint = FastAPIEndpoint.objects.filter(pk=endpoint_id).first()
        if endpoint is None:
            return None, None
        context = get_fastapi_request_context(endpoint_id=endpoint_id)
        return endpoint, context

    count = FastAPIEndpoint.objects.filter(enabled=True).count()
    if count == 0:
        return None, None
    if count == 1:
        endpoint = FastAPIEndpoint.objects.filter(enabled=True).first()
        context = get_fastapi_request_context(endpoint_id=getattr(endpoint, "pk", None))
        return endpoint, context

    endpoint = FastAPIEndpoint.objects.filter(enabled=True).order_by("pk").first()
    if endpoint is None:
        return None, None
    context = get_fastapi_request_context(endpoint_id=getattr(endpoint, "pk", None))
    return endpoint, context


def _build_request_candidates(
    http_url: str,
    ip_address_url: str | None,
    path: str,
    verify_ssl: bool,
) -> list[tuple[str, bool]]:
    """Build list of (url, verify_ssl) candidates for backend requests with fallback."""
    main_url = f"{http_url}/{path}"
    candidates = [(main_url, verify_ssl)]
    if ip_address_url:
        fallback_path = f"{ip_address_url}/{path}"
        if fallback_path != main_url:
            candidates.append((fallback_path, verify_ssl))
    return candidates


def _handle_auth_registration_and_retry(
    backend_headers: dict,
    *,
    endpoint_id: int | None = None,
) -> tuple[dict, bool]:
    """Attempt API key registration with the backend.

    Returns (new_headers, retry_flag). If registration succeeds, returns new headers
    and True to indicate the caller should retry the request.
    """
    from netbox_proxbox.services.backend_auth import ensure_backend_key_registered

    logger.info("Backend returned 'no API key' error; attempting key registration")
    reg_ok, reg_msg = ensure_backend_key_registered(endpoint_id=endpoint_id)
    if reg_ok:
        logger.info("Key registration succeeded: %s", reg_msg)
        new_context = get_fastapi_request_context(endpoint_id=endpoint_id)
        if new_context and new_context.headers:
            return new_context.headers, True
    else:
        logger.warning("Key registration failed: %s", reg_msg)
    return backend_headers, False
