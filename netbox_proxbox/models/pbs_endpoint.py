"""Proxmox Backup Server (PBS) endpoint stored in NetBox for ProxBox sync.

NetBox-side mirror of `proxbox_api.database.PBSEndpoint`. Holds the PBS API
credentials and connection parameters needed for the read-side `/pbs/*`
sync surface in `proxbox-api`.

Read-only integration in v1 (parallels the backend model): `allow_writes` is
reserved for a future write surface and stays `False`.
"""

from __future__ import annotations

from django.db import models
from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext_lazy as _

from netbox_proxbox.models.base import PORT_VALIDATORS, EndpointBase
from netbox_proxbox.models.primary_secrets import (
    decrypt_primary_secret,
    encrypt_primary_secret,
)


class PBSEndpoint(EndpointBase):
    """Credentials and address for a Proxmox Backup Server instance."""

    name = models.CharField(
        default="PBS Endpoint",
        max_length=255,
        blank=True,
        null=True,
        help_text=_("Name of the PBS endpoint. May be updated from the PBS API."),
    )
    port = models.PositiveIntegerField(
        default=8007,
        validators=PORT_VALIDATORS,
        verbose_name=_("HTTP port"),
    )
    token_id = models.CharField(
        max_length=255,
        verbose_name=_("Token ID"),
        help_text=_("PBS API token id of the form 'user@realm!tokenname'."),
    )
    token_secret_enc = models.TextField(
        blank=True,
        default="",
        verbose_name=_("Encrypted token secret"),
        help_text=_("Fernet-encrypted PBS API token secret ciphertext. Internal."),
    )
    fingerprint = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name=_("TLS fingerprint"),
        help_text=_("PBS server TLS fingerprint pinned at connection time. Optional."),
    )
    verify_ssl = models.BooleanField(
        default=True,
        verbose_name=_("Verify SSL"),
        help_text=_("Verify the TLS certificate presented by the PBS endpoint."),
    )
    allow_writes = models.BooleanField(
        default=False,
        verbose_name=_("Allow PBS-side writes"),
        help_text=_(
            "Reserved for a future PBS-side write surface. Default off; "
            "v1 integration is read-only."
        ),
    )
    timeout = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Timeout (seconds)"),
        help_text=_(
            "Per-endpoint API request timeout in seconds. Leave blank for the global default."
        ),
    )
    site = models.ForeignKey(
        to="dcim.Site",
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name=_("Site"),
        null=True,
        blank=True,
    )
    tenant = models.ForeignKey(
        to="tenancy.Tenant",
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name=_("Tenant"),
        null=True,
        blank=True,
    )

    class Meta(EndpointBase.Meta):
        verbose_name = _("PBS endpoint")
        verbose_name_plural = _("PBS endpoints")
        constraints = (
            models.UniqueConstraint(
                fields=("name", "ip_address", "domain"),
                name="netbox_proxbox_pbsendpoint_identity",
            ),
        )

    @property
    def token_secret(self) -> str:
        """Decrypt and return the PBS API token secret."""
        return decrypt_primary_secret(self.token_secret_enc)

    @token_secret.setter
    def token_secret(self, value: object | None) -> None:
        self.token_secret_enc = encrypt_primary_secret(value)

    @property
    def host(self) -> str:
        """Plain hostname string expected by proxbox-api's PBSEndpoint SQLite model.

        proxbox-api stores endpoints with a single ``host`` field; the Django model
        uses ``domain`` and ``ip_address`` from ``EndpointBase``. This property
        provides a compatible value so sync code can use the same field name.
        """
        return self.domain or self.ip or ""

    @property
    def timeout_seconds(self) -> int:
        """Timeout in seconds matching proxbox-api's ``PBSEndpoint.timeout_seconds`` field.

        proxbox-api names the field ``timeout_seconds``; Django uses ``timeout``.
        This property bridges the name difference so sync code can reference either
        model interchangeably.
        """
        return self.timeout if self.timeout is not None else 30

    def get_absolute_url(self) -> str:
        """Plugin UI URL for this PBS endpoint detail view.

        URL routes for the new endpoint models land alongside the form / table /
        view scaffolding in Phase 2 of #449. Until those views are registered,
        gracefully degrade rather than raise ``NoReverseMatch`` if a changelog
        or template helper tries to linkify the row.
        """
        try:
            return reverse("plugins:netbox_proxbox:pbsendpoint", args=[self.pk])
        except NoReverseMatch:
            return ""
