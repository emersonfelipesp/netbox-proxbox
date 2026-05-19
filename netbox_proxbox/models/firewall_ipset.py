"""ProxmoxFirewallIPSet and ProxmoxFirewallIPSetEntry models."""
from __future__ import annotations

from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from netbox.models import NetBoxModel

from netbox_proxbox.choices import FirewallScopeChoices, FirewallSyncStatusChoices


class ProxmoxFirewallIPSet(NetBoxModel):
    """Named Proxmox firewall IP set (datacenter or VM/CT scope)."""

    endpoint = models.ForeignKey(
        to="netbox_proxbox.ProxmoxEndpoint",
        on_delete=models.CASCADE,
        related_name="firewall_ipsets",
        null=True,
        blank=True,
        verbose_name=_("Proxmox endpoint"),
    )
    scope = models.CharField(max_length=16, choices=FirewallScopeChoices)
    virtual_machine = models.ForeignKey(
        to="virtualization.VirtualMachine",
        on_delete=models.CASCADE,
        related_name="proxmox_firewall_ipsets",
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=255)
    comment = models.TextField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=FirewallSyncStatusChoices,
        default=FirewallSyncStatusChoices.ACTIVE,
    )
    raw_config = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = _("Firewall IP Set")
        verbose_name_plural = _("Firewall IP Sets")
        ordering = ("endpoint", "scope", "name")
        constraints = [
            models.UniqueConstraint(
                fields=["endpoint", "scope", "name", "virtual_machine"],
                name="netbox_proxbox_firewallipset_unique_endpoint_scope_name_vm",
            )
        ]

    def __str__(self):
        return f"{self.scope} / {self.name}"

    def get_absolute_url(self):
        return reverse("plugins:netbox_proxbox:proxmoxfirewallipset", args=[self.pk])


class ProxmoxFirewallIPSetEntry(NetBoxModel):
    """A CIDR member entry within a Proxmox firewall IP set."""

    ipset = models.ForeignKey(
        to="netbox_proxbox.ProxmoxFirewallIPSet",
        on_delete=models.CASCADE,
        related_name="entries",
    )
    cidr = models.CharField(max_length=256, help_text=_("Network/IP in CIDR format."))
    comment = models.TextField(null=True, blank=True)
    nomatch = models.BooleanField(
        default=False, help_text=_("Negate/exclude this CIDR from the set.")
    )
    raw_config = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = _("Firewall IP Set Entry")
        verbose_name_plural = _("Firewall IP Set Entries")
        ordering = ("ipset", "cidr")
        constraints = [
            models.UniqueConstraint(
                fields=["ipset", "cidr"],
                name="netbox_proxbox_firewallipsetentry_unique_ipset_cidr",
            )
        ]

    def __str__(self):
        nomatch_prefix = "!" if self.nomatch else ""
        return f"{self.ipset.name}: {nomatch_prefix}{self.cidr}"

    def get_absolute_url(self):
        return reverse("plugins:netbox_proxbox:proxmoxfirewallipsetentry", args=[self.pk])
