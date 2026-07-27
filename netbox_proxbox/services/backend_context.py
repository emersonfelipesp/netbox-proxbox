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
        endpoint_id=context.get("endpoint_id"),
        target_fingerprint=str(context.get("target_fingerprint", "")),
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
        endpoint = FastAPIEndpoint.objects.filter(pk=endpoint_id, enabled=True).first()
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
    context: BackendRequestContext,
    *,
    endpoint_id: int | None = None,
) -> BackendRequestContext | None:
    """Rebind and authenticate one stable endpoint context after a 401.

    The caller must restart candidate selection from the returned context. Returning
    ``None`` fails closed if the endpoint changes again while its key is checked.

    The historical helper name remains part of the backend-proxy contract. It
    never bootstraps or substitutes a credential.
    """
    from netbox_proxbox.services.backend_auth import (
        authenticate_backend_request_context,
    )

    bound_endpoint_id = context.endpoint_id
    if endpoint_id is not None:
        if bound_endpoint_id is not None and bound_endpoint_id != endpoint_id:
            logger.warning("Backend auth retry endpoint identity changed")
            return None
        bound_endpoint_id = endpoint_id
    if bound_endpoint_id is None:
        logger.warning("Backend auth retry has no bound endpoint identity")
        return None

    fresh_context = get_fastapi_request_context(endpoint_id=bound_endpoint_id)
    if fresh_context is None or not fresh_context.http_url or not fresh_context.headers:
        logger.warning(
            "Backend auth retry could not resolve a trusted endpoint context"
        )
        return None

    logger.info("Backend returned an API-key error; re-checking the stored key")
    reg_ok, reg_msg = authenticate_backend_request_context(fresh_context)
    if reg_ok:
        logger.info("Stored key authentication succeeded: %s", reg_msg)
        confirmed_context = get_fastapi_request_context(endpoint_id=bound_endpoint_id)
        if confirmed_context and _request_context_binding(
            confirmed_context
        ) == _request_context_binding(fresh_context):
            return confirmed_context
        logger.warning("Backend endpoint changed during the authentication retry")
    else:
        logger.warning("Stored key authentication failed: %s", reg_msg)
    return None


def _request_context_binding(context: BackendRequestContext) -> tuple[object, ...]:
    """Return every authority and credential field that a retry must preserve."""
    return (
        context.endpoint_id,
        context.target_fingerprint,
        (context.http_url or "").rstrip("/"),
        (context.ip_address_url or "").rstrip("/"),
        bool(context.verify_ssl),
        tuple(sorted((str(key), str(value)) for key, value in context.headers.items())),
    )
