"""Reflected PBS backup group (a logical VM/CT/host backup history)."""

from __future__ import annotations

from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from netbox.models import NetBoxModel

from netbox_pbs.choices import PBSBackupTypeChoices


class PBSBackupGroup(NetBoxModel):
    """A group of snapshots within a datastore — ``{vm,ct,host}/<id>``."""

    datastore = models.ForeignKey(
        to="netbox_pbs.PBSDatastore",
        on_delete=models.CASCADE,
        related_name="backup_groups",
    )
    backup_type = models.CharField(
        max_length=8,
        choices=PBSBackupTypeChoices,
        help_text=_("``vm``, ``ct``, or ``host``."),
    )
    backup_id = models.CharField(
        max_length=64,
        verbose_name=_("Backup ID"),
        help_text=_("PBS group ID — typically the VMID, CTID, or hostname."),
    )
    owner = models.CharField(
        max_length=128,
        blank=True,
        help_text=_("PBS owner principal of this group."),
    )
    comment = models.CharField(
        max_length=512,
        blank=True,
    )

    class Meta:
        ordering = ("datastore", "backup_type", "backup_id")
        verbose_name = _("PBS backup group")
        verbose_name_plural = _("PBS backup groups")
        constraints = (
            models.UniqueConstraint(
                fields=("datastore", "backup_type", "backup_id"),
                name="netbox_pbs_pbsbackupgroup_identity",
            ),
        )

    def __str__(self) -> str:
        return f"{self.datastore} / {self.backup_type}/{self.backup_id}"

    def get_absolute_url(self) -> str:
        return reverse("plugins:netbox_pbs:pbsbackupgroup", args=[self.pk])
