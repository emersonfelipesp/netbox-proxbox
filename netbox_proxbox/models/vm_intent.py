"""Plugin-owned operator intent for a NetBox virtual machine."""

from __future__ import annotations

from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from netbox.models import NetBoxModel


class ProxmoxVMIntent(NetBoxModel):
    """Operator-authored values consumed by the NetBox-to-Proxmox pipeline.

    The UI and API keep an existing row attached to one virtual machine for its
    lifetime so a reassignment cannot leave the former guest stale.
    """

    virtual_machine = models.OneToOneField(
        to="virtualization.VirtualMachine",
        on_delete=models.CASCADE,
        related_name="proxbox_intent",
        help_text=_("NetBox virtual machine governed by this Proxmox intent."),
    )
    target_node = models.CharField(
        max_length=255,
        blank=True,
        help_text=_("Proxmox node that should host this virtual machine."),
    )
    target_storage = models.CharField(
        max_length=255,
        blank=True,
        help_text=_("Proxmox storage used for new virtual-machine disks."),
    )
    iso = models.CharField(
        max_length=255,
        blank=True,
        help_text=_(
            "Optional Proxmox volume ID of the install ISO. Empty means no ISO "
            "is attached on create."
        ),
    )
    template_vmid = models.IntegerField(
        null=True,
        blank=True,
        help_text=_(
            "Source VMID to clone from when creating this VM. Mutually exclusive "
            "with ISO-driven create; both empty means an empty VM."
        ),
    )
    swap = models.IntegerField(
        null=True,
        blank=True,
        help_text=_("LXC swap allocation in MiB."),
    )
    rootfs = models.CharField(
        max_length=255,
        blank=True,
        help_text=_("LXC root filesystem volume specification."),
    )
    ostemplate = models.CharField(
        max_length=255,
        blank=True,
        help_text=_("LXC operating-system template volume ID."),
    )
    cloud_init_user = models.CharField(
        max_length=255,
        blank=True,
        help_text=_(
            "Default cloud-init username. Empty means inherit the Proxmox default."
        ),
    )
    cloud_init_ssh_keys = models.TextField(
        blank=True,
        help_text=_("Newline-separated authorized SSH public keys."),
    )
    cloud_init_user_data = models.TextField(
        blank=True,
        help_text=_("Optional raw cloud-init user-data YAML."),
    )
    cloud_init_network = models.TextField(
        blank=True,
        help_text=_("Optional cloud-init network configuration JSON."),
    )
    intent_state = models.CharField(
        max_length=64,
        blank=True,
        editable=False,
        help_text=_("Last terminal intent verdict written by the apply job."),
    )
    last_apply_run_id = models.CharField(
        max_length=255,
        blank=True,
        editable=False,
        help_text=_("Most recent apply-run UUID written by the apply job."),
    )

    class Meta:
        ordering = ("virtual_machine",)
        verbose_name = _("Proxmox VM intent")
        verbose_name_plural = _("Proxmox VM intents")

    def __str__(self) -> str:
        return f"{self.virtual_machine} Proxmox intent"

    def get_absolute_url(self) -> str:
        return reverse("plugins:netbox_proxbox:proxmoxvmintent", args=[self.pk])
