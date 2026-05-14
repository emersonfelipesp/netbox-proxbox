"""Define the read-only Proxmox cloud-init model stored alongside NetBox virtual machines."""

from __future__ import annotations

from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from netbox.models import NetBoxModel


class ProxmoxVMCloudInit(NetBoxModel):
    """Proxmox cloud-init row mirroring ``ciuser`` / ``sshkeys`` / ``ipconfig0``.

    Populated by proxbox-api from ``qm config <vmid>`` on each sync. Read-only
    on the NetBox side; Proxmox stays the source of truth. ``sshkeys`` is
    stored decoded (newlines as ``\\n``); proxbox-api runs
    ``urllib.parse.unquote`` before writing.
    """

    virtual_machine = models.OneToOneField(
        to="virtualization.VirtualMachine",
        on_delete=models.CASCADE,
        related_name="proxmox_cloudinit",
        help_text=_("NetBox VM this cloud-init record reflects."),
    )

    ciuser = models.CharField(
        max_length=64,
        blank=True,
        help_text=_("Proxmox cloud-init user (``ciuser``)."),
    )

    sshkeys = models.TextField(
        blank=True,
        help_text=_(
            "Decoded cloud-init SSH key bundle (one key per line). "
            "Proxmox-side is URL-encoded; proxbox-api runs urllib.parse.unquote "
            "before writing this row."
        ),
    )

    ipconfig0 = models.CharField(
        max_length=255,
        blank=True,
        help_text=_(
            "Cloud-init first-NIC IP configuration string from Proxmox "
            "(e.g. ``ip=dhcp`` or ``ip=10.0.0.5/24,gw=10.0.0.1``)."
        ),
    )

    sshkeys_truncated = models.BooleanField(
        default=False,
        help_text=_(
            "True when proxbox-api truncated the ``sshkeys`` payload because "
            "the decoded blob exceeded 10 KB."
        ),
    )

    last_synced = models.DateTimeField(
        auto_now=True,
        help_text=_("Time of the last cloud-init reconciliation pass."),
    )

    class Meta:
        verbose_name = _("Proxmox VM cloud-init")
        verbose_name_plural = _("Proxmox VM cloud-init records")
        ordering = ("virtual_machine",)

    def __str__(self) -> str:
        """Return the parent VM name for list displays."""
        return f"{self.virtual_machine} cloud-init"

    def get_absolute_url(self) -> str:
        """Plugin UI URL for this cloud-init record's detail page."""
        return reverse("plugins:netbox_proxbox:proxmoxvmcloudinit", args=[self.pk])
