"""Recorded sync run metadata for ProxBox."""

from __future__ import annotations

from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from netbox.models import NetBoxModel

from netbox_proxbox.choices import SyncStatusChoices, SyncTypeChoices


class SyncProcess(NetBoxModel):
    """High-level sync job type and status as tracked in NetBox."""

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

    def __str__(self) -> str:
        """Name and sync type for tables and log context."""
        return f"{self.name} ({self.sync_type})"

    def get_absolute_url(self) -> str:
        """Plugin UI URL for this sync process record."""
        return reverse("plugins:netbox_proxbox:syncprocess", args=[self.pk])
