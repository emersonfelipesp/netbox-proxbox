"""Proxmox cluster / API endpoint stored in NetBox for ProxBox sync."""

from __future__ import annotations

from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from netbox_proxbox.choices import ProxmoxModeChoices
from netbox_proxbox.fields import DomainField
from netbox_proxbox.models.base import PORT_VALIDATORS, EndpointBase


class ProxmoxEndpoint(EndpointBase):
    """Credentials and address for a Proxmox VE instance or cluster."""

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

    def get_absolute_url(self) -> str:
        return reverse("plugins:netbox_proxbox:proxmoxendpoint", args=[self.pk])
