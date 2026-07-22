"""Django signal handlers for backend-key checks and endpoint synchronization.

FastAPIEndpoint persistence owns candidate validation. These signals only check
already stored keys before downstream synchronization; they never invent or
persist a credential.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.db.models.signals import post_save
from django.dispatch import receiver

if TYPE_CHECKING:
    from netbox_proxbox.models import FastAPIEndpoint, NetBoxEndpoint, ProxmoxEndpoint

logger = logging.getLogger(__name__)


def _get_backend_url(endpoint: FastAPIEndpoint) -> str | None:
    """Return the trusted canonical backend URL, or fail closed."""
    from netbox_proxbox.utils import get_fastapi_url

    detail = get_fastapi_url(endpoint) or {}
    if not isinstance(detail, dict):
        return None
    value = detail.get("http_url")
    return str(value).rstrip("/") if value else None


def _register_token_with_backend(endpoint: FastAPIEndpoint) -> bool:
    """Authenticate the stored key without bootstrapping or persisting it."""
    from netbox_proxbox.services.backend_key_adoption import (
        BackendKeyAdoptionError,
        adopt_rotated_backend_key,
        backend_key_runtime_is_trusted,
    )
    from netbox_proxbox.services.endpoint_enabled import endpoint_is_enabled

    if not endpoint_is_enabled(endpoint):
        logger.info(
            "FastAPIEndpoint %s is disabled, skipping backend key verification",
            getattr(endpoint, "pk", None),
        )
        return False

    if not backend_key_runtime_is_trusted(endpoint):
        logger.warning(
            "FastAPIEndpoint %s target is not covered by its stored key adoption; "
            "backend use is blocked",
            getattr(endpoint, "pk", None),
        )
        return False

    token = (getattr(endpoint, "token", "") or "").strip()
    if not token:
        logger.warning("FastAPIEndpoint %s has no stored API key", endpoint.pk)
        return False

    try:
        proof = adopt_rotated_backend_key(endpoint, token)
    except BackendKeyAdoptionError as exc:
        logger.warning(
            "Backend API key check failed for endpoint %s (%s)",
            endpoint.pk,
            exc.code,
        )
        return False

    logger.info(
        "Backend API key %s for FastAPIEndpoint %s",
        proof.action,
        endpoint.pk,
    )
    return True


@receiver(post_save, sender="netbox_proxbox.FastAPIEndpoint")
def ensure_fastapi_endpoint_token(
    sender: type,
    instance: FastAPIEndpoint,
    created: bool,
    **kwargs: object,
) -> None:
    """Confirm the model-level gate supplied a key before post-save consumers run."""
    from netbox_proxbox.websocket_client import stop_websocket  # noqa: PLC0415

    endpoint = instance
    stop_websocket(int(endpoint.pk))
    if not endpoint.token:
        if bool(getattr(endpoint, "enabled", True)):
            logger.error(
                "FastAPIEndpoint %s was saved without an API key; backend use is blocked",
                endpoint.pk,
            )
        else:
            logger.debug(
                "FastAPIEndpoint %s is disabled and has no staged API key",
                endpoint.pk,
            )
        return
    logger.debug(
        "FastAPIEndpoint %s key transition was handled before persistence",
        endpoint.pk,
    )


@receiver(post_save, sender="netbox_proxbox.ProxmoxEndpoint")
def ensure_proxmox_endpoint_has_fastapi_token(
    sender: type,
    instance: ProxmoxEndpoint,
    created: bool,
    **kwargs: object,
) -> None:
    """Require an adopted FastAPI key before a ProxmoxEndpoint push.

    This receiver never creates, bootstraps, or persists a credential.
    """
    from netbox_proxbox.models import FastAPIEndpoint

    if not bool(getattr(instance, "enabled", True)):
        logger.info(
            "ProxmoxEndpoint %s is disabled, skipping backend key verification and endpoint sync",
            getattr(instance, "pk", None),
        )
        return

    count = FastAPIEndpoint.objects.filter(enabled=True).count()
    if count == 0:
        logger.debug("No enabled FastAPIEndpoint configured, skipping key verification")
        return

    order = FastAPIEndpoint.objects.filter(enabled=True).order_by("pk")
    fastapi_ep = order.first()
    if not fastapi_ep:
        logger.debug("No FastAPIEndpoint found, skipping key verification")
        return

    if count > 1:
        fastapi_ep = order.first()
        logger.debug(
            "Multiple FastAPIEndpoint objects exist (%d), using first by PK: %s",
            count,
            fastapi_ep.pk,
        )

    if not fastapi_ep.token:
        logger.warning(
            "FastAPIEndpoint %s has no API key; Proxmox endpoint sync is blocked",
            fastapi_ep.pk,
        )
        return

    if not _register_token_with_backend(fastapi_ep):
        logger.warning(
            "FastAPIEndpoint %s key is not accepted; Proxmox endpoint sync is blocked",
            fastapi_ep.pk,
        )
        return

    # Also push the Proxmox endpoint data to the backend DB so sync stages can
    # find it without requiring a dashboard visit first.
    base_url = _get_backend_url(fastapi_ep)
    if base_url:
        from netbox_proxbox.utils import get_backend_auth_headers  # noqa: PLC0415

        auth_headers = get_backend_auth_headers(fastapi_ep)
        if not auth_headers:
            logger.warning(
                "FastAPIEndpoint %s has no trusted authentication context; "
                "Proxmox endpoint sync is blocked",
                fastapi_ep.pk,
            )
            return
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

    if not _register_token_with_backend(fastapi_ep):
        logger.warning(
            "FastAPIEndpoint %s key is not accepted; NetBox endpoint sync is blocked",
            fastapi_ep.pk,
        )
        return

    from netbox_proxbox.utils import get_backend_auth_headers  # noqa: PLC0415

    auth_headers = get_backend_auth_headers(fastapi_ep)
    if not auth_headers:
        logger.warning(
            "FastAPIEndpoint %s has no trusted authentication context; "
            "NetBox endpoint sync is blocked",
            fastapi_ep.pk,
        )
        return
    ok, err, _ = _push(
        instance,
        base_url=base_url,
        auth_headers=auth_headers,
        backend_verify_ssl=bool(fastapi_ep.verify_ssl),
    )
    if not ok:
        logger.warning("Could not sync NetBox endpoint to proxbox-api backend: %s", err)
