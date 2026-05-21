"""ProxmoxSdnRouteMap model."""

from __future__ import annotations

from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from netbox.models import NetBoxModel

from netbox_proxbox.choices import FirewallSyncStatusChoices


class ProxmoxSdnRouteMap(NetBoxModel):
    """Proxmox SDN BGP route-map entry."""

    endpoint = models.ForeignKey(
        to="netbox_proxbox.ProxmoxEndpoint",
        on_delete=models.CASCADE,
        related_name="sdn_route_maps",
        null=True,
        blank=True,
        verbose_name=_("Proxmox endpoint"),
    )
    cluster_name = models.CharField(
        max_length=255, help_text=_("Proxmox cluster name.")
    )
    name = models.CharField(max_length=255, help_text=_("Route-map name."))
    action = models.CharField(max_length=16, blank=True, help_text=_("permit or deny."))
    match_peer = models.CharField(max_length=255, blank=True)
    match_ip = models.CharField(max_length=255, blank=True)
    set_community = models.CharField(max_length=255, blank=True)
    order = models.IntegerField(default=0)
    status = models.CharField(
        max_length=20,
        choices=FirewallSyncStatusChoices,
        default=FirewallSyncStatusChoices.ACTIVE,
    )
    raw_config = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = _("SDN Route Map")
        verbose_name_plural = _("SDN Route Maps")
        ordering = ("endpoint", "cluster_name", "name", "order")
        constraints = [
            models.UniqueConstraint(
                fields=["endpoint", "cluster_name", "name", "order"],
                name="netbox_proxbox_sdnroutemap_unique_endpoint_cluster_name_order",
            )
        ]

    def __str__(self):
        return f"{self.cluster_name} / {self.name}"

    def get_absolute_url(self):
        return reverse("plugins:netbox_proxbox:proxmoxsdnroutemap", args=[self.pk])
