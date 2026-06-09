"""Django signal handlers for automatic token generation and backend registration.

These signals ensure FastAPIEndpoint tokens are generated and registered with
the proxbox-api backend automatically when endpoints are created or updated.
They also push NetBoxEndpoint configuration to the proxbox-api internal database
so the backend can bootstrap a NetBox session on startup.
"""

from __future__ import annotations

import logging
import secrets
from typing import TYPE_CHECKING

from django.db.models.signals import post_save
from django.dispatch import receiver

if TYPE_CHECKING:
    from netbox_proxbox.models import FastAPIEndpoint, NetBoxEndpoint, ProxmoxEndpoint

logger = logging.getLogger(__name__)


def _get_backend_url(endpoint: FastAPIEndpoint) -> str | None:
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

    scheme = "https" if endpoint.use_https else "http"
    return f"{scheme}://{host}:{endpoint.port}"


def _register_token_with_backend(endpoint: FastAPIEndpoint) -> bool | None:
    """Attempt to register the endpoint's token with the proxbox-api backend.

    This is a best-effort operation that logs failures but never raises exceptions.
    """
    import requests
    from netbox_proxbox.services.endpoint_enabled import endpoint_is_enabled

    if not endpoint_is_enabled(endpoint):
        logger.info(
            "FastAPIEndpoint %s is disabled, skipping backend token registration",
            getattr(endpoint, "pk", None),
        )
        return False

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
    sender: type,
    instance: FastAPIEndpoint,
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
    sender: type,
    instance: ProxmoxEndpoint,
    created: bool,
    **kwargs: object,
) -> None:
    """Ensure there's a FastAPIEndpoint with a token when ProxmoxEndpoint is saved.

    This catches the upgrade scenario where migration ran but backend was offline.
    When user saves ProxmoxEndpoint to configure sync, we ensure the FastAPIEndpoint
    has a token and it's registered.
    """
    from netbox_proxbox.models import FastAPIEndpoint

    if not bool(getattr(instance, "enabled", True)):
        logger.info(
            "ProxmoxEndpoint %s is disabled, skipping backend token registration and endpoint sync",
            getattr(instance, "pk", None),
        )
        return

    count = FastAPIEndpoint.objects.filter(enabled=True).count()
    if count == 0:
        logger.debug(
            "No enabled FastAPIEndpoint configured, skipping token registration"
        )
        return

    order = FastAPIEndpoint.objects.filter(enabled=True).order_by("pk")
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

    # Also push the Proxmox endpoint data to the backend DB so sync stages can
    # find it without requiring a dashboard visit first.
    base_url = _get_backend_url(fastapi_ep)
    if base_url:
        auth_headers = {"X-Proxbox-API-Key": (fastapi_ep.token or "").strip()}
        from netbox_proxbox.views.backend_sync import sync_proxmox_endpoint_to_backend  # noqa: PLC0415

        ok, err, _ = sync_proxmox_endpoint_to_backend(
            instance,
            base_url=base_url,
            auth_headers=auth_headers,
            backend_verify_ssl=bool(fastapi_ep.verify_ssl),
        )
        if ok:
            logger.info(
                "Synced Proxmox endpoint '%s' to proxbox-api backend after save",
                getattr(instance, "name", instance.pk),
            )
        else:
            logger.warning(
                "Could not sync Proxmox endpoint '%s' to proxbox-api backend: %s",
                getattr(instance, "name", instance.pk),
                err,
            )


@receiver(post_save, sender="netbox_proxbox.NetBoxEndpoint")
def sync_netbox_endpoint_to_backend(
    sender: type,
    instance: NetBoxEndpoint,
    created: bool,
    **kwargs: object,
) -> None:
    """Push the saved NetBoxEndpoint configuration to the proxbox-api internal database.

    proxbox-api needs a NetBox endpoint record in its own SQLite database to
    bootstrap a NetBox session.  This signal ensures the record is created or
    updated automatically whenever the plugin's NetBoxEndpoint is saved.
    """
    from netbox_proxbox.models import FastAPIEndpoint
    from netbox_proxbox.views.backend_sync import (
        sync_netbox_endpoint_to_backend as _push,
    )  # noqa: PLC0415

    if not bool(getattr(instance, "enabled", True)):
        logger.info(
            "NetBoxEndpoint %s is disabled, skipping backend endpoint sync",
            getattr(instance, "pk", None),
        )
        return

    fastapi_ep = FastAPIEndpoint.objects.filter(enabled=True).order_by("pk").first()
    if not fastapi_ep:
        logger.debug(
            "No enabled FastAPIEndpoint configured, skipping NetBox endpoint sync"
        )
        return

    base_url = _get_backend_url(fastapi_ep)
    if not base_url:
        logger.debug(
            "Cannot push NetBox endpoint: no backend URL configured for FastAPIEndpoint %s",
            fastapi_ep.pk,
        )
        return

    auth_headers = {"X-Proxbox-API-Key": (fastapi_ep.token or "").strip()}
    ok, err, _ = _push(
        instance,
        base_url=base_url,
        auth_headers=auth_headers,
        backend_verify_ssl=bool(fastapi_ep.verify_ssl),
    )
    if not ok:
        logger.warning("Could not sync NetBox endpoint to proxbox-api backend: %s", err)
