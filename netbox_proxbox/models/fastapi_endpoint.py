"""ProxBox FastAPI (proxbox-api) backend endpoint configuration."""

from __future__ import annotations

from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from netbox_proxbox.fields import DomainField
from netbox_proxbox.models.base import PORT_VALIDATORS, EndpointBase


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

    def get_absolute_url(self) -> str:
        """Plugin UI URL for this FastAPI endpoint detail view."""
        return reverse("plugins:netbox_proxbox:fastapiendpoint", args=[self.pk])
