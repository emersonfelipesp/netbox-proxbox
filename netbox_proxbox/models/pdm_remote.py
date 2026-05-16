"""Discovered PDM remote: one row of PDM's `/pdm/remotes` reflected in NetBox.

Each remote represents either a PVE cluster or a PBS instance that the PDM
federates. The optional FK columns `linked_proxmox_endpoint` and
`linked_pbs_endpoint` are the **discovered truth** populated by the sync
job after matching on hostname / fingerprint; the **operator-declared
truth** lives on `PDMEndpoint.proxmox_endpoints` / `pbs_endpoints`.

Drift between the two surfaces is rendered as a warning on the
`PDMEndpoint` detail page in a follow-up UI PR (Phase 3 per issue #449).
"""

from __future__ import annotations

from django.db import models
from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext_lazy as _

from netbox.models import NetBoxModel


class PDMRemoteTypeChoices(models.TextChoices):
    PVE = "pve", _("PVE")
    PBS = "pbs", _("PBS")


class PDMRemote(NetBoxModel):
    """One PDM-managed remote (PVE cluster or PBS instance)."""

    pdm_endpoint = models.ForeignKey(
        to="netbox_proxbox.PDMEndpoint",
        on_delete=models.CASCADE,
        related_name="remotes",
        verbose_name=_("PDM endpoint"),
        help_text=_("PDMEndpoint this remote is discovered from."),
    )
    name = models.CharField(
        max_length=255,
        verbose_name=_("Remote name"),
        help_text=_("Remote name as reported by PDM."),
    )
    type = models.CharField(
        max_length=8,
        choices=PDMRemoteTypeChoices.choices,
        verbose_name=_("Type"),
        help_text=_("Whether this remote is a PVE cluster or a PBS instance."),
    )
    hostname = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_("Hostname"),
        help_text=_("Primary hostname reported by PDM for this remote."),
    )
    fingerprint = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_("TLS fingerprint"),
    )
    version = models.CharField(
        max_length=64,
        blank=True,
        verbose_name=_("Reported version"),
    )
    linked_proxmox_endpoint = models.ForeignKey(
        to="netbox_proxbox.ProxmoxEndpoint",
        on_delete=models.SET_NULL,
        related_name="pdm_remotes",
        null=True,
        blank=True,
        verbose_name=_("Linked PVE endpoint"),
        help_text=_(
            "Auto-resolved PVE endpoint matched on hostname/fingerprint. "
            "Set only when type='pve'."
        ),
    )
    linked_pbs_endpoint = models.ForeignKey(
        to="netbox_proxbox.PBSEndpoint",
        on_delete=models.SET_NULL,
        related_name="pdm_remotes",
        null=True,
        blank=True,
        verbose_name=_("Linked PBS endpoint"),
        help_text=_(
            "Auto-resolved PBS endpoint matched on hostname/fingerprint. "
            "Set only when type='pbs'."
        ),
    )
    last_seen_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Last seen at"),
    )

    class Meta:
        ordering = ("pdm_endpoint", "name")
        verbose_name = _("PDM remote")
        verbose_name_plural = _("PDM remotes")
        constraints = [
            models.UniqueConstraint(
                fields=("pdm_endpoint", "name"),
                name="netbox_proxbox_pdmremote_unique_endpoint_name",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.type}, {self.pdm_endpoint})"

    def clean(self) -> None:
        """Enforce typed-link invariant: exactly one of linked_* matches `type`."""
        super().clean()
        from django.core.exceptions import ValidationError

        if self.type == "pve" and self.linked_pbs_endpoint_id:
            raise ValidationError(
                {"linked_pbs_endpoint": "Only allowed when type='pbs'."}
            )
        if self.type == "pbs" and self.linked_proxmox_endpoint_id:
            raise ValidationError(
                {"linked_proxmox_endpoint": "Only allowed when type='pve'."}
            )

    def get_absolute_url(self) -> str:
        """Plugin UI URL for this PDM remote detail view.

        URL routes land in Phase 2 of #449; until then, degrade gracefully
        rather than raise ``NoReverseMatch`` if a changelog or template
        helper tries to linkify the row.
        """
        try:
            return reverse("plugins:netbox_proxbox:pdmremote", args=[self.pk])
        except NoReverseMatch:
            return ""
