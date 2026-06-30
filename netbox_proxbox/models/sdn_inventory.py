"""Additional Proxmox SDN inventory models."""

from __future__ import annotations

from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from netbox.models import NetBoxModel

from netbox_proxbox.choices import FirewallSyncStatusChoices


class ProxmoxSdnController(NetBoxModel):
    """Proxmox SDN controller metadata."""

    endpoint = models.ForeignKey(
        to="netbox_proxbox.ProxmoxEndpoint",
        on_delete=models.CASCADE,
        related_name="sdn_controllers",
        null=True,
        blank=True,
        verbose_name=_("Proxmox endpoint"),
    )
    cluster_name = models.CharField(max_length=255)
    controller_name = models.CharField(max_length=255)
    controller_type = models.CharField(max_length=32, blank=True)
    asn = models.IntegerField(null=True, blank=True)
    peers = models.JSONField(default=list, blank=True)
    nodes = models.JSONField(default=list, blank=True)
    loopback = models.CharField(max_length=255, blank=True)
    state = models.CharField(max_length=32, blank=True)
    status = models.CharField(
        max_length=20,
        choices=FirewallSyncStatusChoices,
        default=FirewallSyncStatusChoices.ACTIVE,
    )
    raw_config = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = _("SDN Controller")
        verbose_name_plural = _("SDN Controllers")
        ordering = ("endpoint", "cluster_name", "controller_name")
        constraints = [
            models.UniqueConstraint(
                fields=["endpoint", "cluster_name", "controller_name"],
                name="nbpx_sdncontroller_unique_endpoint_cluster_name",
            )
        ]

    def __str__(self):
        return f"{self.cluster_name} / {self.controller_name}"

    def get_absolute_url(self):
        return reverse("plugins:netbox_proxbox:proxmoxsdncontroller", args=[self.pk])


class ProxmoxSdnZone(NetBoxModel):
    """Proxmox SDN zone metadata."""

    endpoint = models.ForeignKey(
        to="netbox_proxbox.ProxmoxEndpoint",
        on_delete=models.CASCADE,
        related_name="sdn_zones",
        null=True,
        blank=True,
        verbose_name=_("Proxmox endpoint"),
    )
    cluster_name = models.CharField(max_length=255)
    zone_name = models.CharField(max_length=255)
    zone_type = models.CharField(max_length=32, blank=True)
    controller = models.CharField(max_length=255, blank=True)
    vrf_vxlan = models.IntegerField(null=True, blank=True)
    tag = models.IntegerField(null=True, blank=True)
    mtu = models.IntegerField(null=True, blank=True)
    dns = models.CharField(max_length=255, blank=True)
    ipam = models.CharField(max_length=255, blank=True)
    rt_import = models.JSONField(default=list, blank=True)
    state = models.CharField(max_length=32, blank=True)
    status = models.CharField(
        max_length=20,
        choices=FirewallSyncStatusChoices,
        default=FirewallSyncStatusChoices.ACTIVE,
    )
    raw_config = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = _("SDN Zone")
        verbose_name_plural = _("SDN Zones")
        ordering = ("endpoint", "cluster_name", "zone_name")
        constraints = [
            models.UniqueConstraint(
                fields=["endpoint", "cluster_name", "zone_name"],
                name="nbpx_sdnzone_unique_endpoint_cluster_name",
            )
        ]

    def __str__(self):
        return f"{self.cluster_name} / {self.zone_name}"

    def get_absolute_url(self):
        return reverse("plugins:netbox_proxbox:proxmoxsdnzone", args=[self.pk])


class ProxmoxSdnVNet(NetBoxModel):
    """Proxmox SDN VNet metadata linked to NetBox L2VPN when managed."""

    endpoint = models.ForeignKey(
        to="netbox_proxbox.ProxmoxEndpoint",
        on_delete=models.CASCADE,
        related_name="sdn_vnets",
        null=True,
        blank=True,
        verbose_name=_("Proxmox endpoint"),
    )
    cluster_name = models.CharField(max_length=255)
    zone_name = models.CharField(max_length=255, blank=True)
    vnet_name = models.CharField(max_length=255)
    vnet_type = models.CharField(max_length=32, blank=True)
    tag = models.IntegerField(null=True, blank=True)
    alias = models.CharField(max_length=255, blank=True)
    vlanaware = models.BooleanField(default=False)
    state = models.CharField(max_length=32, blank=True)
    l2vpn = models.ForeignKey(
        to="vpn.L2VPN",
        on_delete=models.SET_NULL,
        related_name="+",
        null=True,
        blank=True,
        verbose_name=_("NetBox L2VPN"),
    )
    status = models.CharField(
        max_length=20,
        choices=FirewallSyncStatusChoices,
        default=FirewallSyncStatusChoices.ACTIVE,
    )
    raw_config = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = _("SDN VNet")
        verbose_name_plural = _("SDN VNets")
        ordering = ("endpoint", "cluster_name", "zone_name", "vnet_name")
        constraints = [
            models.UniqueConstraint(
                fields=["endpoint", "cluster_name", "vnet_name"],
                name="nbpx_sdnvnet_unique_endpoint_cluster_name",
            )
        ]

    def __str__(self):
        return f"{self.cluster_name} / {self.zone_name} / {self.vnet_name}"

    def get_absolute_url(self):
        return reverse("plugins:netbox_proxbox:proxmoxsdnvnet", args=[self.pk])


class ProxmoxSdnSubnet(NetBoxModel):
    """Proxmox SDN subnet metadata linked to NetBox Prefix when valid."""

    endpoint = models.ForeignKey(
        to="netbox_proxbox.ProxmoxEndpoint",
        on_delete=models.CASCADE,
        related_name="sdn_subnets",
        null=True,
        blank=True,
        verbose_name=_("Proxmox endpoint"),
    )
    cluster_name = models.CharField(max_length=255)
    zone_name = models.CharField(max_length=255, blank=True)
    vnet_name = models.CharField(max_length=255)
    subnet = models.CharField(max_length=128)
    subnet_type = models.CharField(max_length=32, blank=True)
    gateway = models.CharField(max_length=128, blank=True)
    snat = models.BooleanField(default=False)
    prefix = models.ForeignKey(
        to="ipam.Prefix",
        on_delete=models.SET_NULL,
        related_name="+",
        null=True,
        blank=True,
        verbose_name=_("NetBox prefix"),
    )
    skip_reason = models.TextField(blank=True)
    status = models.CharField(
        max_length=20,
        choices=FirewallSyncStatusChoices,
        default=FirewallSyncStatusChoices.ACTIVE,
    )
    raw_config = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = _("SDN Subnet")
        verbose_name_plural = _("SDN Subnets")
        ordering = ("endpoint", "cluster_name", "vnet_name", "subnet")
        constraints = [
            models.UniqueConstraint(
                fields=["endpoint", "cluster_name", "vnet_name", "subnet"],
                name="nbpx_sdnsubnet_unique_endpoint_cluster_vnet_subnet",
            )
        ]

    def __str__(self):
        return f"{self.cluster_name} / {self.vnet_name} / {self.subnet}"

    def get_absolute_url(self):
        return reverse("plugins:netbox_proxbox:proxmoxsdnsubnet", args=[self.pk])


class ProxmoxSdnBinding(NetBoxModel):
    """SDN sync binding/status record for runtime rows and NetBox object links."""

    endpoint = models.ForeignKey(
        to="netbox_proxbox.ProxmoxEndpoint",
        on_delete=models.CASCADE,
        related_name="sdn_bindings",
        null=True,
        blank=True,
        verbose_name=_("Proxmox endpoint"),
    )
    cluster_name = models.CharField(max_length=255)
    source_type = models.CharField(max_length=64)
    source_name = models.CharField(max_length=512)
    node = models.CharField(max_length=255, blank=True)
    zone_name = models.CharField(max_length=255, blank=True)
    vnet_name = models.CharField(max_length=255, blank=True)
    target_type = models.CharField(max_length=64, blank=True)
    target_id = models.PositiveBigIntegerField(null=True, blank=True)
    status = models.CharField(
        max_length=64,
        default=FirewallSyncStatusChoices.ACTIVE,
    )
    conflict_reason = models.TextField(blank=True)
    raw_config = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = _("SDN Binding")
        verbose_name_plural = _("SDN Bindings")
        ordering = ("endpoint", "cluster_name", "source_type", "source_name")
        constraints = [
            models.UniqueConstraint(
                fields=["endpoint", "cluster_name", "source_type", "source_name"],
                name="nbpx_sdnbinding_unique_endpoint_cluster_source",
            )
        ]

    def __str__(self):
        return f"{self.cluster_name} / {self.source_type} / {self.source_name}"

    def get_absolute_url(self):
        return reverse("plugins:netbox_proxbox:proxmoxsdnbinding", args=[self.pk])
