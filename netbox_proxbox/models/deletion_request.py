"""Shell ``DeletionRequest`` model for the NetBox→Proxmox safe-delete flow.

Sub-PR B introduces only the minimal field set required to register the model
plus the ``authorize_deletion_request`` permission in migration 0038. The full
14-field schema (state machine, metadata snapshot, requester/authorizer/executor
attribution, TTL, executor stamps) lands in Sub-PR H
(``0041_deletion_request_full``).
"""

from __future__ import annotations

from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from netbox.models import NetBoxModel


class DeletionRequest(NetBoxModel):
    """Represents a pending Proxmox DELETE awaiting four-eyes authorization.

    Promoted to its full schema in Sub-PR H. The shell exists now so the
    ``netbox_proxbox.authorize_deletion_request`` permission registered in
    migration ``0038_intent_permissions`` attaches to a real ContentType
    distinct from the ``intent_delete_*`` permissions on ``ProxmoxApplyJob``.
    The two permissions stay independent by design — four-eyes requires that
    the user who *requests* a delete cannot be the user who *approves* it.
    """

    name = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_("Name"),
        help_text=_("Optional human-readable label for the deletion request."),
    )

    class Meta:
        ordering = ("-pk",)
        verbose_name = _("Deletion Request")
        verbose_name_plural = _("Deletion Requests")
        permissions = (
            (
                "authorize_deletion_request",
                "Can authorize (approve/reject) a Proxmox DeletionRequest",
            ),
        )

    def __str__(self) -> str:
        return self.name or f"DeletionRequest #{self.pk}"

    def get_absolute_url(self) -> str:
        return reverse("plugins:netbox_proxbox:deletionrequest", args=[self.pk])
