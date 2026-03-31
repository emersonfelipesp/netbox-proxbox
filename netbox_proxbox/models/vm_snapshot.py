"""Define the VM snapshot model stored alongside NetBox virtual machines."""

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.urls import reverse

from netbox.models import NetBoxModel

from netbox_proxbox.choices import (
    ProxmoxSnapshotSubtypeChoices,
    ProxmoxSnapshotStatusChoices,
)


class VMSnapshot(NetBoxModel):
    """Proxmox snapshot row linked to a NetBox ``VirtualMachine``."""

    proxmox_storage = models.ForeignKey(
        to="netbox_proxbox.ProxmoxStorage",
        on_delete=models.SET_NULL,
        related_name="vm_snapshots",
        null=True,
        blank=True,
        help_text=_("Related Proxmox storage object."),
    )

    virtual_machine = models.ForeignKey(
        to="virtualization.VirtualMachine",
        on_delete=models.CASCADE,
        related_name="snapshots",
    )

    name = models.CharField(
        max_length=255,
        help_text=_("Snapshot name."),
    )

    description = models.TextField(
        null=True,
        blank=True,
        help_text=_("Snapshot description."),
    )

    vmid = models.IntegerField(
        help_text=_("Proxmox VM ID."),
    )

    node = models.CharField(
        max_length=255,
        help_text=_("Proxmox node name."),
    )

    snaptime = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("Snapshot creation time."),
    )

    parent = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text=_("Parent snapshot name."),
    )

    subtype = models.CharField(
        max_length=255,
        choices=ProxmoxSnapshotSubtypeChoices,
        default=ProxmoxSnapshotSubtypeChoices.SNAPSHOT_SUBTYPE_QEMU,
    )

    status = models.CharField(
        max_length=255,
        choices=ProxmoxSnapshotStatusChoices,
        default=ProxmoxSnapshotStatusChoices.SNAPSHOT_STATUS_ACTIVE,
    )

    class Meta:
        verbose_name = "VM Snapshot"
        verbose_name_plural = "VM Snapshots"
        ordering = ("virtual_machine", "node", "name")
        unique_together = ("vmid", "name", "node")

    def __str__(self):
        """VM and snapshot name for list displays."""
        return f"{self.virtual_machine} - {self.name}"

    def get_absolute_url(self):
        """Plugin UI URL for this snapshot's detail page."""
        return reverse("plugins:netbox_proxbox:vmsnapshot", args=[self.pk])
