"""ProxmoxSdnPrefixList model."""

from __future__ import annotations

from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from netbox.models import NetBoxModel

from netbox_proxbox.choices import FirewallSyncStatusChoices


class ProxmoxSdnPrefixList(NetBoxModel):
    """Proxmox SDN BGP prefix-list entry."""

    endpoint = models.ForeignKey(
        to="netbox_proxbox.ProxmoxEndpoint",
        on_delete=models.CASCADE,
        related_name="sdn_prefix_lists",
        null=True,
        blank=True,
        verbose_name=_("Proxmox endpoint"),
    )
    cluster_name = models.CharField(max_length=255, help_text=_("Proxmox cluster name."))
    name = models.CharField(max_length=255, help_text=_("Prefix-list name."))
    cidr = models.CharField(max_length=64, blank=True, help_text=_("CIDR prefix."))
    action = models.CharField(max_length=16, blank=True, help_text=_("permit or deny."))
    le = models.IntegerField(null=True, blank=True, help_text=_("Less-or-equal prefix length."))
    ge = models.IntegerField(null=True, blank=True, help_text=_("Greater-or-equal prefix length."))
    status = models.CharField(
        max_length=20,
        choices=FirewallSyncStatusChoices,
        default=FirewallSyncStatusChoices.ACTIVE,
    )
    raw_config = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = _("SDN Prefix List")
        verbose_name_plural = _("SDN Prefix Lists")
        ordering = ("endpoint", "cluster_name", "name")
        constraints = [
            models.UniqueConstraint(
                fields=["endpoint", "cluster_name", "name"],
                name="netbox_proxbox_sdnprefixlist_unique_endpoint_cluster_name",
            )
        ]

    def __str__(self):
        return f"{self.cluster_name} / {self.name}"

    def get_absolute_url(self):
        return reverse("plugins:netbox_proxbox:proxmoxsdnprefixlist", args=[self.pk])
