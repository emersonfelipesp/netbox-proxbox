"""Persisted PBS API endpoint for the netbox-pbs plugin.

Mirrors the credential-storage pattern from
``netbox_proxbox.models.ProxmoxEndpoint``: plaintext CharFields for the
API token, gated by NetBox RBAC. No encryption-at-rest is invented here;
operator-facing protection lives in the existing ``view``/``change`` model
permissions and ``ObjectPermissionRequiredMixin`` enforcement.

v1 is **read-only PBS → NetBox**; there is no ``allow_writes`` field on
the NetBox side because there is no NetBox → PBS write path to gate.
The mirror flag lives in ``proxbox-api`` (``PBSEndpoint.allow_writes``)
and stays locked ``False`` for v1.
"""

from __future__ import annotations

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from netbox.models import NetBoxModel


class PBSEndpoint(NetBoxModel):
    """Proxmox Backup Server endpoint registered in NetBox."""

    name = models.CharField(
        max_length=255,
        unique=True,
        help_text=_("Friendly name for this PBS endpoint."),
    )
    host = models.CharField(
        max_length=255,
        help_text=_(
            "PBS hostname or IP. A plain string keeps standalone install "
            "viable when ``ipam`` is not pre-populated."
        ),
    )
    port = models.PositiveIntegerField(
        default=8007,
        validators=(MinValueValidator(1), MaxValueValidator(65535)),
        verbose_name=_("HTTP port"),
    )
    token_id = models.CharField(
        max_length=255,
        verbose_name=_("Token ID"),
        help_text=_("PBS API token ID in the form ``user@realm!tokenname``."),
    )
    token_value = models.CharField(
        max_length=255,
        verbose_name=_("Token value"),
        help_text=_("PBS API token secret. Protected by NetBox object-level RBAC."),
    )
    fingerprint = models.CharField(
        max_length=128,
        blank=True,
        verbose_name=_("Certificate fingerprint"),
        help_text=_(
            "Optional SHA-256 fingerprint of the PBS API TLS certificate "
            "(``aa:bb:...``). When set, pinned by the proxbox-api PBS client."
        ),
    )
    verify_ssl = models.BooleanField(
        default=True,
        verbose_name=_("Verify SSL"),
    )
    timeout = models.PositiveIntegerField(
        default=30,
        verbose_name=_("Timeout (seconds)"),
        help_text=_("Per-endpoint API request timeout used by proxbox-api."),
    )
    last_seen_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Last seen at"),
        help_text=_("Updated by the read-only PBS sync after a successful probe."),
    )

    class Meta:
        ordering = ("name", "pk")
        verbose_name = _("PBS endpoint")
        verbose_name_plural = _("PBS endpoints")

    def __str__(self) -> str:
        return self.name or f"PBSEndpoint({self.pk})"

    def get_absolute_url(self) -> str:
        return reverse("plugins:netbox_pbs:pbsendpoint", args=[self.pk])
