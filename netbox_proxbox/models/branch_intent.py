"""Plugin-owned safety gates for an optional netbox-branching branch."""

from __future__ import annotations

from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from netbox.models import NetBoxModel


class ProxboxBranchIntent(NetBoxModel):
    """Intent gates keyed by a soft reference to a branching plugin row.

    The optional ``netbox_branching`` package is deliberately not imported by
    this model. The integer primary key and schema identifier are resolved only
    at runtime, so this plugin retains no schema dependency on the companion.
    """

    branch_id = models.PositiveBigIntegerField(
        help_text=_("Soft reference to the netbox-branching Branch primary key."),
    )
    branch_schema_id = models.CharField(
        max_length=8,
        help_text=_("Soft reference to the netbox-branching Branch schema ID."),
    )
    apply_to_proxmox = models.BooleanField(
        default=False,
        help_text=_("Opt this branch into the NetBox-to-Proxmox intent pipeline."),
    )
    apply_destroy_confirmed = models.BooleanField(
        default=False,
        help_text=_(
            "Allow DELETE diffs to produce deletion requests for separate "
            "authorization."
        ),
    )

    class Meta:
        ordering = ("branch_id",)
        verbose_name = _("Proxbox branch intent")
        verbose_name_plural = _("Proxbox branch intents")
        constraints = (
            models.UniqueConstraint(
                fields=("branch_id", "branch_schema_id"),
                name="netbox_proxbox_branch_intent_reference_unique",
            ),
        )

    def __str__(self) -> str:
        """Identify the soft-referenced branch without resolving it."""
        return f"Branch {self.branch_id} ({self.branch_schema_id}) intent"

    def get_absolute_url(self) -> str:
        """Return this intent row's plugin detail URL."""
        return reverse("plugins:netbox_proxbox:proxboxbranchintent", args=[self.pk])

    def resolve_branch(self):
        """Resolve the optional companion row, returning ``None`` on failure."""
        from netbox_proxbox.services.branch_intent import resolve_branch_reference

        return resolve_branch_reference(self.branch_id, self.branch_schema_id)
