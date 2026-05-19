"""ProxmoxFirewallAlias model."""

from __future__ import annotations

from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from netbox.models import NetBoxModel

from netbox_proxbox.choices import FirewallScopeChoices, FirewallSyncStatusChoices


class ProxmoxFirewallAlias(NetBoxModel):
    """Named Proxmox firewall IP alias (datacenter or VM/CT scope)."""

    endpoint = models.ForeignKey(
        to="netbox_proxbox.ProxmoxEndpoint",
        on_delete=models.CASCADE,
        related_name="firewall_aliases",
        null=True,
        blank=True,
        verbose_name=_("Proxmox endpoint"),
    )
    scope = models.CharField(max_length=16, choices=FirewallScopeChoices)
    virtual_machine = models.ForeignKey(
        to="virtualization.VirtualMachine",
        on_delete=models.CASCADE,
        related_name="proxmox_firewall_aliases",
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=255)
    cidr = models.CharField(max_length=256, help_text=_("Network/IP in CIDR format."))
    comment = models.TextField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=FirewallSyncStatusChoices,
        default=FirewallSyncStatusChoices.ACTIVE,
    )

    class Meta:
        verbose_name = _("Firewall Alias")
        verbose_name_plural = _("Firewall Aliases")
        ordering = ("endpoint", "scope", "name")
        constraints = [
            models.UniqueConstraint(
                fields=["endpoint", "scope", "name", "virtual_machine"],
                name="netbox_proxbox_firewallalias_unique_endpoint_scope_name_vm",
            )
        ]

    def __str__(self):
        return f"{self.scope} / {self.name} ({self.cidr})"

    def get_absolute_url(self):
        return reverse("plugins:netbox_proxbox:proxmoxfirewallalias", args=[self.pk])
