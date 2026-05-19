"""ProxmoxFirewallOptions model."""

from __future__ import annotations

from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from netbox.models import NetBoxModel

from netbox_proxbox.choices import FirewallZoneChoices


class ProxmoxFirewallOptions(NetBoxModel):
    """Firewall options snapshot for a Proxmox firewall zone."""

    endpoint = models.ForeignKey(
        to="netbox_proxbox.ProxmoxEndpoint",
        on_delete=models.CASCADE,
        related_name="firewall_options",
        null=True,
        blank=True,
        verbose_name=_("Proxmox endpoint"),
    )
    zone = models.CharField(max_length=20, choices=FirewallZoneChoices)
    proxmox_node = models.ForeignKey(
        to="netbox_proxbox.ProxmoxNode",
        on_delete=models.SET_NULL,
        related_name="firewall_options",
        null=True,
        blank=True,
    )
    virtual_machine = models.ForeignKey(
        to="virtualization.VirtualMachine",
        on_delete=models.CASCADE,
        related_name="proxmox_firewall_options",
        null=True,
        blank=True,
    )
    enable = models.BooleanField(
        null=True, blank=True, help_text=_("Firewall enable flag for this zone.")
    )
    policy_in = models.CharField(
        max_length=16, blank=True, help_text=_("Input policy: ACCEPT/DROP/REJECT.")
    )
    policy_out = models.CharField(
        max_length=16, blank=True, help_text=_("Output policy: ACCEPT/DROP/REJECT.")
    )
    options = models.JSONField(
        default=dict,
        blank=True,
        help_text=_(
            "Zone-specific options (nosmurfs, tcpflags, conntrack, dhcp, ipfilter, etc.)."
        ),
    )
    raw_config = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = _("Firewall Options")
        verbose_name_plural = _("Firewall Options")
        ordering = ("endpoint", "zone")
        constraints = [
            models.UniqueConstraint(
                fields=["endpoint", "zone", "proxmox_node", "virtual_machine"],
                name="netbox_proxbox_firewalloptions_unique_endpoint_zone_node_vm",
            )
        ]

    def __str__(self):
        return f"{self.endpoint} / {self.zone} options"

    def get_absolute_url(self):
        return reverse("plugins:netbox_proxbox:proxmoxfirewalloptions", args=[self.pk])
