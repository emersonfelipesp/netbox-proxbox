"""ProxBox FastAPI (proxbox-api) backend endpoint configuration."""

from __future__ import annotations

import logging
import secrets

import requests as _requests
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from netbox_proxbox.fields import DomainField
from netbox_proxbox.models.base import PORT_VALIDATORS, EndpointBase

logger = logging.getLogger(__name__)


class FastAPIEndpoint(EndpointBase):
    """HTTP/WebSocket reachability and optional auth for the ProxBox backend."""

    name = models.CharField(
        default="ProxBox Endpoint",
        max_length=255,
        blank=True,
        null=True,
        help_text=_("Name of the ProxBox backend endpoint."),
    )
    ip_address = models.ForeignKey(
        to="ipam.IPAddress",
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name=_("IP address"),
        null=True,
        blank=True,
        help_text=_("Fallback backend address when no domain name is configured."),
    )
    domain = DomainField(
        blank=True,
        null=True,
        verbose_name=_("Domain"),
        help_text=_("Domain name of the ProxBox backend service."),
    )
    port = models.PositiveIntegerField(
        default=8800,
        validators=PORT_VALIDATORS,
        verbose_name=_("HTTP port"),
    )
    verify_ssl = models.BooleanField(
        default=True,
        verbose_name=_("Verify SSL"),
        help_text=_("Verify the TLS certificate presented by the ProxBox backend."),
    )
    token = models.CharField(
        blank=True,
        null=True,
        max_length=255,
        verbose_name=_("Token"),
        help_text=_("Optional backend token used by the ProxBox service."),
    )
    use_websocket = models.BooleanField(
        default=False,
        verbose_name=_("Use WebSocket"),
        help_text=_("Use WebSocket connectivity for browser updates."),
    )
    websocket_domain = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name=_("WebSocket domain"),
        help_text=_("Domain name used for browser WebSocket connections."),
    )
    websocket_port = models.PositiveIntegerField(
        default=8800,
        validators=PORT_VALIDATORS,
        verbose_name=_("WebSocket port"),
        help_text=_("Port used for WebSocket connectivity."),
    )
    server_side_websocket = models.BooleanField(
        default=False,
        verbose_name=_("Server-side WebSocket"),
        help_text=_(
            "Use server-side WebSocket connectivity when supported by the backend."
        ),
    )

    class Meta(EndpointBase.Meta):
        verbose_name = _("FastAPI endpoint")
        verbose_name_plural = _("FastAPI endpoints")
        constraints = (
            models.UniqueConstraint(
                fields=("name", "ip_address"),
                name="netbox_proxbox_fastapiendpoint_identity",
            ),
        )

    @property
    def websocket_url(self) -> str:
        """``ws(s)://`` URL for browser or server WebSocket clients."""
        protocol = "wss" if self.verify_ssl else "ws"
        host = self.websocket_domain or self.domain or self.ip
        return f"{protocol}://{host}:{self.websocket_port}" if host else ""

    def save(self, *args: object, **kwargs: object) -> None:
        is_new_token = not (self.token or "").strip()
        if is_new_token:
            self.token = secrets.token_urlsafe(48)
        super().save(*args, **kwargs)
        if is_new_token:
            self._register_key_with_backend()

    def _register_key_with_backend(self) -> None:
        """Best-effort: register the auto-generated token with the proxbox-api backend."""
        from netbox_proxbox.utils import get_fastapi_url

        try:
            url_info = get_fastapi_url(self)
            base_url = url_info.get("http_url") or url_info.get("ip_address_url")
            if not base_url:
                logger.warning("No FastAPI URL configured, cannot register API key.")
                return

            # Check if bootstrap is needed
            status_url = f"{base_url}/auth/bootstrap-status"
            try:
                status_response = _requests.get(
                    status_url, verify=self.verify_ssl, timeout=5
                )
                if status_response.status_code == 200:
                    status_data = status_response.json()
                    if not status_data.get("needs_bootstrap", False):
                        logger.debug(
                            "proxbox-api already has API key configured; skipping registration."
                        )
                        return
            except Exception as exc:
                logger.debug("Could not check bootstrap status: %s", exc)

            # Register the key
            response = _requests.post(
                f"{base_url}/auth/register-key",
                json={"api_key": self.token, "label": str(self)},
                verify=self.verify_ssl,
                timeout=10,
            )
            if response.status_code == 201:
                logger.info("Successfully registered API key with proxbox-api backend.")
            elif response.status_code == 409:
                logger.info(
                    "proxbox-api already has an API key configured; skipping registration."
                )
            elif response.status_code >= 500:
                logger.warning(
                    "proxbox-api key registration failed (server error %s): %s",
                    response.status_code,
                    response.text[:200],
                )
            else:
                logger.debug(
                    "proxbox-api key registration returned %s: %s",
                    response.status_code,
                    response.text[:200] if response.text else "",
                )
        except _requests.exceptions.ConnectionError as exc:
            logger.warning(
                "Could not register API key with proxbox-api (connection refused): %s",
                exc,
            )
        except _requests.exceptions.Timeout as exc:
            logger.warning(
                "Could not register API key with proxbox-api (timeout): %s", exc
            )
        except Exception as exc:
            logger.warning(
                "Could not register API key with proxbox-api backend: %s", exc
            )

    def get_absolute_url(self) -> str:
        """Plugin UI URL for this FastAPI endpoint detail view."""
        return reverse("plugins:netbox_proxbox:fastapiendpoint", args=[self.pk])
