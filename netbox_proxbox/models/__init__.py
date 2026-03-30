"""Define endpoint and sync-process models used throughout the plugin."""

from django.core.validators import MaxValueValidator, MinValueValidator
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from netbox.models import NetBoxModel

from netbox_proxbox.choices import (
    NetBoxTokenVersionChoices,
    ProxmoxModeChoices,
    SyncStatusChoices,
    SyncTypeChoices,
)
from netbox_proxbox.fields import DomainField
from netbox_proxbox.models.vm_backup import VMBackup
from netbox_proxbox.models.vm_snapshot import VMSnapshot


PORT_VALIDATORS = (MinValueValidator(1), MaxValueValidator(65535))


class CommonProperties:
    @property
    def ip(self) -> str | None:
        return str(self.ip_address.address.ip) if self.ip_address else None

    @property
    def url(self) -> str:
        protocol = "https" if self.verify_ssl else "http"
        host = self.domain or self.ip
        return f"{protocol}://{host}:{self.port}" if host else ""


class EndpointBase(CommonProperties, NetBoxModel):
    name = models.CharField(
        max_length=255,
        blank=True,
        null=True,
    )
    ip_address = models.ForeignKey(
        to="ipam.IPAddress",
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name=_("IP address"),
        null=True,
        blank=True,
    )
    domain = DomainField(
        verbose_name=_("Domain"),
        blank=True,
        null=True,
    )
    port = models.PositiveIntegerField(
        validators=PORT_VALIDATORS,
        verbose_name=_("HTTP port"),
    )
    verify_ssl = models.BooleanField(
        verbose_name=_("Verify SSL"),
    )

    class Meta:
        abstract = True
        ordering = ("name", "pk")

    def __str__(self):
        return self.name or self.domain or self.ip or self.__class__.__name__

    def clean(self):
        super().clean()
        if not (self.domain or self.ip_address_id):
            raise ValidationError(
                {
                    "domain": "Provide either a domain or an IP address.",
                    "ip_address": "Provide either a domain or an IP address.",
                }
            )


class ProxmoxEndpoint(EndpointBase):
    name = models.CharField(
        default="Proxmox Endpoint",
        max_length=255,
        blank=True,
        null=True,
        help_text=_(
            "Name of the Proxmox endpoint or cluster. It may be updated from the API."
        ),
    )
    ip_address = models.ForeignKey(
        to="ipam.IPAddress",
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name=_("IP address"),
        null=True,
        blank=True,
        help_text=_("Fallback endpoint address when no domain name is configured."),
    )
    domain = DomainField(
        verbose_name=_("Domain"),
        help_text=_("Domain name of the Proxmox endpoint or cluster."),
        blank=True,
        null=True,
    )
    port = models.PositiveIntegerField(
        default=8006,
        validators=PORT_VALIDATORS,
        verbose_name=_("HTTP port"),
    )
    mode = models.CharField(
        max_length=255,
        choices=ProxmoxModeChoices,
        default=ProxmoxModeChoices.PROXMOX_MODE_UNDEFINED,
    )
    version = models.CharField(max_length=20, blank=True, null=True)
    repoid = models.CharField(
        max_length=16,
        blank=True,
        null=True,
        verbose_name=_("Repository ID"),
    )
    username = models.CharField(
        default="root@pam",
        max_length=255,
        verbose_name=_("Username"),
        help_text=_("Username must use the format 'user@realm'."),
    )
    password = models.CharField(
        max_length=255,
        verbose_name=_("Password"),
        help_text=_(
            "Password for the Proxmox endpoint. Leave blank when using token authentication."
        ),
        blank=True,
        null=True,
    )
    token_name = models.CharField(
        max_length=255,
        verbose_name=_("Token name"),
        blank=True,
    )
    token_value = models.CharField(
        max_length=255,
        verbose_name=_("Token value"),
        blank=True,
    )
    verify_ssl = models.BooleanField(
        default=False,
        verbose_name=_("Verify SSL"),
        help_text=_("Verify the TLS certificate presented by the Proxmox endpoint."),
    )

    class Meta(EndpointBase.Meta):
        verbose_name = _("Proxmox endpoint")
        verbose_name_plural = _("Proxmox endpoints")
        constraints = (
            models.UniqueConstraint(
                fields=("name", "ip_address", "domain"),
                name="netbox_proxbox_proxmoxendpoint_identity",
            ),
        )

    def get_absolute_url(self):
        return reverse("plugins:netbox_proxbox:proxmoxendpoint", args=[self.pk])


class NetBoxEndpoint(EndpointBase):
    name = models.CharField(
        default="NetBox Endpoint",
        max_length=255,
        blank=True,
        null=True,
        help_text=_("Name of the remote NetBox endpoint."),
    )
    ip_address = models.ForeignKey(
        to="ipam.IPAddress",
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name=_("IP address"),
        null=True,
        blank=True,
        help_text=_("Fallback API address when no domain name is configured."),
    )
    domain = DomainField(
        blank=True,
        null=True,
        verbose_name=_("Domain"),
        help_text=_("Domain name of the remote NetBox API."),
    )
    port = models.PositiveIntegerField(
        default=443,
        validators=PORT_VALIDATORS,
        verbose_name=_("HTTP port"),
    )
    token = models.ForeignKey(
        to="users.Token",
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name=_("API token"),
        null=True,
        blank=True,
        help_text=_(
            "Token used by the ProxBox backend when communicating with NetBox."
        ),
    )
    token_version = models.CharField(
        max_length=2,
        choices=NetBoxTokenVersionChoices,
        default=NetBoxTokenVersionChoices.V1,
        verbose_name=_("Token Version"),
        help_text=_(
            "Choose whether to authenticate using a v1 token or a v2 token key/secret pair."
        ),
    )
    token_key = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_("Token Key"),
        help_text=_("Key portion of a NetBox v2 API token."),
    )
    token_secret = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_("Token Secret"),
        help_text=_("Secret portion of a NetBox v2 API token."),
    )
    verify_ssl = models.BooleanField(
        default=True,
        verbose_name=_("Verify SSL"),
        help_text=_("Verify the TLS certificate presented by the NetBox API."),
    )

    class Meta(EndpointBase.Meta):
        verbose_name = _("NetBox endpoint")
        verbose_name_plural = _("NetBox endpoints")
        constraints = (
            models.UniqueConstraint(
                fields=("name", "ip_address"),
                name="netbox_proxbox_netboxendpoint_identity",
            ),
        )

    @property
    def effective_token_version(self) -> str:
        token_obj = getattr(self, "token", None)
        if token_obj is not None:
            return (
                NetBoxTokenVersionChoices.V2
                if getattr(token_obj, "version", None) == 2
                else NetBoxTokenVersionChoices.V1
            )
        return self.token_version

    @property
    def effective_token_value(self) -> str | None:
        token_obj = getattr(self, "token", None)
        if token_obj is not None:
            if self.effective_token_version == NetBoxTokenVersionChoices.V2:
                return getattr(token_obj, "key", None)
            return getattr(token_obj, "plaintext", None) or getattr(
                token_obj, "key", None
            )

        if self.effective_token_version == NetBoxTokenVersionChoices.V2:
            return self.token_key or None
        return None

    @property
    def has_configured_token(self) -> bool:
        if self.token is not None:
            return True
        if self.effective_token_version == NetBoxTokenVersionChoices.V2:
            return bool(self.token_key and self.token_secret)
        return False

    @property
    def token_version_label(self) -> str:
        return (
            "v2 Token"
            if self.effective_token_version == NetBoxTokenVersionChoices.V2
            else "v1 Token"
        )

    def get_absolute_url(self):
        return reverse("plugins:netbox_proxbox:netboxendpoint", args=[self.pk])


class FastAPIEndpoint(EndpointBase):
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
        protocol = "wss" if self.verify_ssl else "ws"
        host = self.websocket_domain or self.domain or self.ip
        return f"{protocol}://{host}:{self.websocket_port}" if host else ""

    def get_absolute_url(self):
        return reverse("plugins:netbox_proxbox:fastapiendpoint", args=[self.pk])


class SyncProcess(NetBoxModel):
    name = models.CharField(max_length=255, unique=True)
    sync_type = models.CharField(
        max_length=20,
        choices=SyncTypeChoices,
        default=SyncTypeChoices.ALL,
    )
    status = models.CharField(
        max_length=20,
        choices=SyncStatusChoices,
        default=SyncStatusChoices.NOT_STARTED,
    )
    started_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("When the sync process started."),
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("When the sync process completed."),
    )
    runtime = models.FloatField(
        null=True,
        blank=True,
        help_text=_("Time elapsed for the sync process in seconds."),
    )

    class Meta:
        ordering = ("-created", "-pk")

    def __str__(self):
        return f"{self.name} ({self.sync_type})"

    def get_absolute_url(self):
        return reverse("plugins:netbox_proxbox:syncprocess", args=[self.pk])


__all__ = (
    "FastAPIEndpoint",
    "NetBoxEndpoint",
    "ProxmoxEndpoint",
    "SyncProcess",
    "VMBackup",
    "VMSnapshot",
)
