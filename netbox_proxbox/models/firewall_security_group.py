"""ProxmoxFirewallSecurityGroup model."""

from __future__ import annotations

from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from netbox.models import NetBoxModel

from netbox_proxbox.choices import FirewallSyncStatusChoices


class ProxmoxFirewallSecurityGroup(NetBoxModel):
    """Cluster-scoped Proxmox firewall security group (named rule set)."""

    endpoint = models.ForeignKey(
        to="netbox_proxbox.ProxmoxEndpoint",
        on_delete=models.CASCADE,
        related_name="firewall_security_groups",
        null=True,
        blank=True,
        verbose_name=_("Proxmox endpoint"),
    )
    name = models.CharField(max_length=255, help_text=_("Security group name."))
    comment = models.TextField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=FirewallSyncStatusChoices,
        default=FirewallSyncStatusChoices.ACTIVE,
    )
    raw_config = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = _("Firewall Security Group")
        verbose_name_plural = _("Firewall Security Groups")
        ordering = ("endpoint", "name")
        constraints = [
            models.UniqueConstraint(
                fields=["endpoint", "name"],
                name="netbox_proxbox_firewallsecuritygroup_unique_endpoint_name",
            )
        ]

    def __str__(self):
        return f"{self.endpoint} / {self.name}"

    def get_absolute_url(self):
        return reverse(
            "plugins:netbox_proxbox:proxmoxfirewallsecuritygroup", args=[self.pk]
        )
