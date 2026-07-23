"""Remote NetBox API endpoint used by the ProxBox backend."""

from __future__ import annotations

from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from netbox_proxbox.choices import NetBoxTokenVersionChoices
from netbox_proxbox.fields import DomainField
from netbox_proxbox.models.base import PORT_VALIDATORS, EndpointBase


class NetBoxEndpoint(EndpointBase):
    """Target NetBox installation the ProxBox service reads and writes."""

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
    pushed_credential_fingerprint = models.CharField(
        max_length=64,
        blank=True,
        default="",
        editable=False,
        verbose_name=_("Pushed credential fingerprint"),
        help_text=_(
            "Non-reversible fingerprint of the credentials last successfully "
            "pushed to the ProxBox backend. Maintained automatically by the "
            "push itself; used to detect a token rotated since that push."
        ),
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
        """Resolved v1 vs v2 from linked ``Token`` when present, else ``token_version`` field."""
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
        """Best-effort credential string for API calls (FK token or v2 key field)."""
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
        """True if a selectable token or a complete v2 key/secret pair is stored."""
        if self.token is not None:
            return True
        if self.effective_token_version == NetBoxTokenVersionChoices.V2:
            return bool(self.token_key and self.token_secret)
        return False

    @property
    def token_version_label(self) -> str:
        """Short UI label for the effective token style."""
        return (
            "v2 Token"
            if self.effective_token_version == NetBoxTokenVersionChoices.V2
            else "v1 Token"
        )

    def get_absolute_url(self) -> str:
        """Plugin UI URL for this NetBox endpoint detail view."""
        return reverse("plugins:netbox_proxbox:netboxendpoint", args=[self.pk])
