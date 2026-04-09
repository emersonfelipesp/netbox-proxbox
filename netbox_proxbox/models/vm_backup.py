"""Define the VM backup model stored alongside NetBox virtual machines."""

from __future__ import annotations

# Django Imports
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.urls import reverse

# NetBox Imports
from netbox.models import NetBoxModel

# NetBox ProxBox Imports
from netbox_proxbox.choices import (
    ProxmoxBackupSubtypeChoices,
    ProxmoxBackupFormatChoices,
)


class VMBackup(NetBoxModel):
    """Proxmox backup metadata attached to a NetBox ``VirtualMachine``."""

    proxmox_storage = models.ForeignKey(
        to="netbox_proxbox.ProxmoxStorage",
        on_delete=models.SET_NULL,
        related_name="vm_backups",
        null=True,
        blank=True,
        help_text=_("Related Proxmox storage object."),
    )

    storage = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text=_("Storage of the backup."),
    )

    virtual_machine = models.ForeignKey(
        to="virtualization.VirtualMachine",
        on_delete=models.CASCADE,
        related_name="backups",
    )

    subtype = models.CharField(
        max_length=255,
        choices=ProxmoxBackupSubtypeChoices,
        default=ProxmoxBackupSubtypeChoices.BACKUP_SUBTYPE_UNDEFINED,
    )

    format = models.CharField(
        max_length=255,
        choices=ProxmoxBackupFormatChoices,
        default=ProxmoxBackupFormatChoices.BACKUP_FORMAT_UNDEFINED,
    )

    creation_time = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("Creation time of the backup."),
    )

    size = models.BigIntegerField(
        null=True,
        blank=True,
        help_text=_("Size in bytes of the backup."),
    )

    notes = models.TextField(
        null=True,
        blank=True,
        help_text=_("Notes of the backup."),
    )

    volume_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text=_("Volume Identifier of the backup."),
    )

    vmid = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=_("VM ID of the backup."),
    )

    used = models.BigIntegerField(
        null=True,
        blank=True,
        help_text=_("Used space of the backup."),
    )

    encrypted = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text=_(
            "Encryption fingerprint or flag from Proxmox (empty = not encrypted)."
        ),
    )

    verification_state = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text=_("Verification state of the backup."),
    )

    verification_upid = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text=_("Verification UPID of the backup."),
    )

    class Meta:
        verbose_name = "VM Backup"
        verbose_name_plural = "VM Backups"
        ordering = ("storage", "virtual_machine", "creation_time")
        constraints = [
            models.UniqueConstraint(
                fields=(
                    "storage",
                    "virtual_machine",
                    "subtype",
                    "format",
                    "volume_id",
                    "vmid",
                ),
                name="unique_vm_backup_fields",
            ),
        ]

    def __str__(self) -> str:
        """VM and backup creation timestamp for list displays."""
        if self.creation_time:
            return f"{self.virtual_machine} - {self.creation_time}"
        return f"{self.virtual_machine} - {self.volume_id}"

    def get_absolute_url(self) -> str:
        """Plugin UI URL for this backup's detail page."""
        return reverse("plugins:netbox_proxbox:vmbackup", args=[self.pk])
