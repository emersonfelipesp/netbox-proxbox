"""Reflected PBS snapshot record."""

from __future__ import annotations

from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from netbox.models import NetBoxModel
from utilities.json import CustomFieldJSONEncoder

from netbox_pbs.choices import PBSSnapshotVerifyChoices


class PBSSnapshot(NetBoxModel):
    """One PBS snapshot inside a backup group."""

    backup_group = models.ForeignKey(
        to="netbox_pbs.PBSBackupGroup",
        on_delete=models.CASCADE,
        related_name="snapshots",
    )
    backup_time = models.DateTimeField(
        verbose_name=_("Backup time (UTC)"),
        help_text=_("Snapshot creation timestamp from PBS (epoch → UTC)."),
    )
    size_bytes = models.BigIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Size (bytes)"),
    )
    encrypted = models.BooleanField(
        default=False,
    )
    verified = models.CharField(
        max_length=16,
        choices=PBSSnapshotVerifyChoices,
        default=PBSSnapshotVerifyChoices.VERIFY_NONE,
    )
    protected = models.BooleanField(
        default=False,
        help_text=_("PBS ``protected`` flag — snapshot is excluded from prune."),
    )
    comment = models.CharField(
        max_length=512,
        blank=True,
    )
    files = models.JSONField(
        default=list,
        blank=True,
        encoder=CustomFieldJSONEncoder,
        help_text=_("PBS file manifest (``[{filename, size, crypt-mode}, ...]``)."),
    )

    class Meta:
        ordering = ("backup_group", "-backup_time")
        verbose_name = _("PBS snapshot")
        verbose_name_plural = _("PBS snapshots")
        constraints = (
            models.UniqueConstraint(
                fields=("backup_group", "backup_time"),
                name="netbox_pbs_pbssnapshot_identity",
            ),
        )

    def __str__(self) -> str:
        return f"{self.backup_group} @ {self.backup_time.isoformat()}"

    def get_absolute_url(self) -> str:
        return reverse("plugins:netbox_pbs:pbssnapshot", args=[self.pk])
