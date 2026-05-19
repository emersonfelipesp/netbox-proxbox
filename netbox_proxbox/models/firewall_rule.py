"""ProxmoxFirewallRule model."""

from __future__ import annotations

from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from netbox.models import NetBoxModel

from netbox_proxbox.choices import (
    FirewallLogLevelChoices,
    FirewallRuleTypeChoices,
    FirewallSyncStatusChoices,
    FirewallZoneChoices,
)


class ProxmoxFirewallRule(NetBoxModel):
    """A single Proxmox firewall rule at any zone level."""

    endpoint = models.ForeignKey(
        to="netbox_proxbox.ProxmoxEndpoint",
        on_delete=models.CASCADE,
        related_name="firewall_rules",
        null=True,
        blank=True,
        verbose_name=_("Proxmox endpoint"),
    )
    zone = models.CharField(
        max_length=20,
        choices=FirewallZoneChoices,
        help_text=_("Firewall zone this rule belongs to."),
    )
    proxmox_node = models.ForeignKey(
        to="netbox_proxbox.ProxmoxNode",
        on_delete=models.SET_NULL,
        related_name="firewall_rules",
        null=True,
        blank=True,
        help_text=_("Node — set for node-level rules."),
    )
    virtual_machine = models.ForeignKey(
        to="virtualization.VirtualMachine",
        on_delete=models.CASCADE,
        related_name="proxmox_firewall_rules",
        null=True,
        blank=True,
        help_text=_("VM/CT — set for VM-level rules."),
    )
    security_group = models.ForeignKey(
        to="netbox_proxbox.ProxmoxFirewallSecurityGroup",
        on_delete=models.CASCADE,
        related_name="rules",
        null=True,
        blank=True,
        help_text=_("Security group — set for security-group rules."),
    )
    pos = models.PositiveIntegerField(help_text=_("Rule position in the ruleset."))
    rule_type = models.CharField(
        max_length=16,
        choices=FirewallRuleTypeChoices,
        help_text=_("Rule direction/type."),
    )
    action = models.CharField(
        max_length=128,
        help_text=_("ACCEPT, DROP, REJECT, or security group name."),
    )
    enable = models.BooleanField(default=True, help_text=_("Rule enabled flag."))
    macro = models.CharField(
        max_length=128, blank=True, help_text=_("Predefined macro name.")
    )
    iface = models.CharField(
        max_length=64, blank=True, help_text=_("Network interface.")
    )
    source = models.CharField(
        max_length=512, blank=True, help_text=_("Source address/IP set/alias.")
    )
    dest = models.CharField(
        max_length=512, blank=True, help_text=_("Destination address/IP set/alias.")
    )
    proto = models.CharField(max_length=32, blank=True, help_text=_("IP protocol."))
    dport = models.CharField(
        max_length=128, blank=True, help_text=_("Destination port(s).")
    )
    sport = models.CharField(max_length=128, blank=True, help_text=_("Source port(s)."))
    log = models.CharField(
        max_length=16,
        choices=FirewallLogLevelChoices,
        blank=True,
        help_text=_("Per-rule log level."),
    )
    icmp_type = models.CharField(
        max_length=64, blank=True, help_text=_("ICMP type (when proto is icmp).")
    )
    comment = models.TextField(null=True, blank=True)
    digest = models.CharField(
        max_length=64, blank=True, help_text=_("Proxmox concurrency token.")
    )
    status = models.CharField(
        max_length=20,
        choices=FirewallSyncStatusChoices,
        default=FirewallSyncStatusChoices.ACTIVE,
    )
    raw_config = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = _("Firewall Rule")
        verbose_name_plural = _("Firewall Rules")
        ordering = ("endpoint", "zone", "pos")
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "endpoint",
                    "zone",
                    "pos",
                    "proxmox_node",
                    "virtual_machine",
                    "security_group",
                ],
                name="netbox_proxbox_firewallrule_unique_endpoint_zone_pos",
            )
        ]

    def __str__(self):
        return f"{self.zone} / pos {self.pos}: {self.rule_type} {self.action}"

    def get_absolute_url(self):
        return reverse("plugins:netbox_proxbox:proxmoxfirewallrule", args=[self.pk])
