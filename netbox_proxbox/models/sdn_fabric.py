"""ProxmoxSdnFabric model."""

from __future__ import annotations

from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from netbox.models import NetBoxModel

from netbox_proxbox.choices import FirewallSyncStatusChoices, SdnFabricTypeChoices


class ProxmoxSdnFabric(NetBoxModel):
    """Proxmox SDN fabric definition (BGP, WireGuard, VXLAN, or OSPF)."""

    endpoint = models.ForeignKey(
        to="netbox_proxbox.ProxmoxEndpoint",
        on_delete=models.CASCADE,
        related_name="sdn_fabrics",
        null=True,
        blank=True,
        verbose_name=_("Proxmox endpoint"),
    )
    cluster_name = models.CharField(max_length=255, help_text=_("Proxmox cluster name."))
    fabric_name = models.CharField(max_length=255, help_text=_("SDN fabric identifier."))
    fabric_type = models.CharField(
        max_length=32,
        choices=SdnFabricTypeChoices,
        help_text=_("SDN fabric type."),
    )
    asn = models.IntegerField(null=True, blank=True, help_text=_("BGP ASN."))
    advertise_subnets = models.BooleanField(default=False)
    disable_arp_nd_suppression = models.BooleanField(default=False)
    vrf_vxlan = models.IntegerField(null=True, blank=True, help_text=_("VRF VXLAN ID."))
    peers = models.JSONField(default=list, blank=True)
    status = models.CharField(
        max_length=20,
        choices=FirewallSyncStatusChoices,
        default=FirewallSyncStatusChoices.ACTIVE,
    )
    raw_config = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = _("SDN Fabric")
        verbose_name_plural = _("SDN Fabrics")
        ordering = ("endpoint", "cluster_name", "fabric_name")
        constraints = [
            models.UniqueConstraint(
                fields=["endpoint", "cluster_name", "fabric_name"],
                name="netbox_proxbox_sdnfabric_unique_endpoint_cluster_fabric",
            )
        ]

    def __str__(self):
        return f"{self.cluster_name} / {self.fabric_name}"

    def get_absolute_url(self):
        return reverse("plugins:netbox_proxbox:proxmoxsdnfabric", args=[self.pk])
