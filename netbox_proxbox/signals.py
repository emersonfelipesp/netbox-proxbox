"""Django signal handlers for automatic token generation and backend registration.

These signals ensure FastAPIEndpoint tokens are generated and registered with
the proxbox-api backend automatically when endpoints are created or updated.
"""

import logging
import secrets

from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


def _get_backend_url(endpoint: object) -> str | None:
    """Build the base URL for the proxbox-api backend from a FastAPIEndpoint."""
    if not endpoint:
        return None

    host = None
    if endpoint.domain:
        host = endpoint.domain
    elif endpoint.ip_address:
        host = str(endpoint.ip_address.address).split("/")[0]

    if not host:
        return None

    scheme = "https" if endpoint.verify_ssl else "http"
    return f"{scheme}://{host}:{endpoint.port}"


def _register_token_with_backend(endpoint: object) -> bool | None:
    """Attempt to register the endpoint's token with the proxbox-api backend.

    This is a best-effort operation that logs failures but never raises exceptions.
    """
    import requests

    base_url = _get_backend_url(endpoint)
    if not base_url:
        logger.debug(
            "Cannot register token: no backend URL configured for endpoint %s",
            endpoint.pk,
        )
        return False

    token = (getattr(endpoint, "token", "") or "").strip()
    if not token:
        logger.debug("Cannot register token: endpoint %s has no token", endpoint.pk)
        return False

    try:
        status_resp = requests.get(
            f"{base_url}/auth/bootstrap-status",
            verify=endpoint.verify_ssl,
            timeout=5,
        )
        if status_resp.status_code != 200:
            logger.warning(
                "Bootstrap status check failed for endpoint %s: HTTP %s",
                endpoint.pk,
                status_resp.status_code,
            )
            return False

        status_data = status_resp.json()
        if not status_data.get("needs_bootstrap", False):
            logger.debug(
                "Endpoint %s: backend already has API key registered", endpoint.pk
            )
            return True

    except requests.exceptions.RequestException as exc:
        logger.warning(
            "Could not check bootstrap status for endpoint %s: %s", endpoint.pk, exc
        )
        return False

    try:
        register_resp = requests.post(
            f"{base_url}/auth/register-key",
            json={"api_key": token, "label": f"netbox-fastapi-{endpoint.pk}"},
            verify=endpoint.verify_ssl,
            timeout=10,
        )
        if register_resp.status_code == 201:
            logger.info(
                "Successfully registered API key for endpoint %s with backend",
                endpoint.pk,
            )
            return True
        if register_resp.status_code == 409:
            logger.debug(
                "Endpoint %s: backend already has API key registered", endpoint.pk
            )
            return True
        logger.warning(
            "Failed to register API key for endpoint %s: HTTP %s - %s",
            endpoint.pk,
            register_resp.status_code,
            register_resp.text[:200],
        )
        return False

    except requests.exceptions.RequestException as exc:
        logger.warning(
            "Could not register API key for endpoint %s: %s", endpoint.pk, exc
        )
        return False


@receiver(post_save, sender="netbox_proxbox.FastAPIEndpoint")
def ensure_fastapi_endpoint_token(
    sender: object,
    instance: object,
    created: bool,
    **kwargs: object,
) -> None:
    """Ensure FastAPIEndpoint has a token and register it with the backend.

    This signal:
    1. Generates a token if none exists
    2. Registers the token with the proxbox-api backend (best-effort)
    """
    from netbox_proxbox.models import FastAPIEndpoint

    endpoint = instance

    if not endpoint.token:
        logger.info("FastAPIEndpoint %s has no token, generating one", endpoint.pk)
        endpoint.token = secrets.token_urlsafe(48)
        FastAPIEndpoint.objects.filter(pk=endpoint.pk).update(token=endpoint.token)

    _register_token_with_backend(endpoint)


@receiver(post_save, sender="netbox_proxbox.ProxmoxEndpoint")
def ensure_proxmox_endpoint_has_fastapi_token(
    sender: object,
    instance: object,
    created: bool,
    **kwargs: object,
) -> None:
    """Ensure there's a FastAPIEndpoint with a token when ProxmoxEndpoint is saved.

    This catches the upgrade scenario where migration ran but backend was offline.
    When user saves ProxmoxEndpoint to configure sync, we ensure the FastAPIEndpoint
    has a token and it's registered.
    """
    from netbox_proxbox.models import FastAPIEndpoint

    count = FastAPIEndpoint.objects.count()
    if count == 0:
        logger.debug("No FastAPIEndpoint configured, skipping token registration")
        return

    order = FastAPIEndpoint.objects.order_by("pk")
    fastapi_ep = order.first()
    if not fastapi_ep:
        logger.debug("No FastAPIEndpoint found, skipping token registration")
        return

    if count > 1:
        fastapi_ep = order.first()
        logger.debug(
            "Multiple FastAPIEndpoint objects exist (%d), using first by PK: %s",
            count,
            fastapi_ep.pk,
        )

    if not fastapi_ep.token:
        logger.info(
            "FastAPIEndpoint %s has no token (detected during ProxmoxEndpoint save), generating one",
            fastapi_ep.pk,
        )
        fastapi_ep.token = secrets.token_urlsafe(48)
        FastAPIEndpoint.objects.filter(pk=fastapi_ep.pk).update(token=fastapi_ep.token)

    _register_token_with_backend(fastapi_ep)
