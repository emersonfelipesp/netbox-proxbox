"""Proxmox node tracking and linkage to NetBox dcim.Device."""

from __future__ import annotations

from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from netbox.models import NetBoxModel


class ProxmoxNode(NetBoxModel):
    """
    Tracks Proxmox node (hypervisor) information synced from a ProxmoxEndpoint.
    Links to NetBox's native dcim.Device for integration.
    """

    endpoint = models.ForeignKey(
        to="netbox_proxbox.ProxmoxEndpoint",
        on_delete=models.CASCADE,
        related_name="proxmox_nodes",
        verbose_name=_("Proxmox endpoint"),
        help_text=_("ProxmoxEndpoint this node is discovered from."),
    )
    proxmox_cluster = models.ForeignKey(
        to="netbox_proxbox.ProxmoxCluster",
        on_delete=models.SET_NULL,
        related_name="nodes",
        verbose_name=_("Proxmox cluster"),
        null=True,
        blank=True,
        help_text=_("ProxmoxCluster this node belongs to (null for standalone)."),
    )
    netbox_device = models.ForeignKey(
        to="dcim.Device",
        on_delete=models.SET_NULL,
        related_name="proxmox_node_tracking",
        verbose_name=_("NetBox device"),
        null=True,
        blank=True,
        help_text=_("Linked NetBox device object created during device sync."),
    )
    name = models.CharField(
        max_length=255,
        verbose_name=_("Node name"),
        help_text=_("Proxmox node hostname."),
    )
    node_id = models.IntegerField(
        null=True,
        blank=True,
        verbose_name=_("Node ID"),
        help_text=_("Corosync node ID (null for standalone nodes)."),
    )
    ip_address = models.GenericIPAddressField(
        verbose_name=_("IP address"),
        help_text=_("Node IP address."),
    )
    online = models.BooleanField(
        default=False,
        verbose_name=_("Online"),
        help_text=_("Whether the node is currently online."),
    )
    local = models.BooleanField(
        default=False,
        verbose_name=_("Local node"),
        help_text=_("Whether this is the local node of the cluster."),
    )
    cpu_usage = models.FloatField(
        null=True,
        blank=True,
        verbose_name=_("CPU usage"),
        help_text=_("CPU utilization percentage."),
    )
    max_cpu = models.IntegerField(
        null=True,
        blank=True,
        verbose_name=_("Max CPU"),
        help_text=_("Number of CPU cores available."),
    )
    memory_usage = models.BigIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Memory usage"),
        help_text=_("Used memory in bytes."),
    )
    max_memory = models.BigIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Max memory"),
        help_text=_("Total memory available in bytes."),
    )
    ssl_fingerprint = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_("SSL fingerprint"),
        help_text=_("SSL certificate fingerprint."),
    )
    support_level = models.CharField(
        max_length=100,
        blank=True,
        verbose_name=_("Support level"),
        help_text=_("Proxmox subscription/support level."),
    )

    class Meta:
        ordering = ("endpoint", "name")
        verbose_name = _("Proxmox node")
        verbose_name_plural = _("Proxmox nodes")
        constraints = [
            models.UniqueConstraint(
                fields=["endpoint", "name"],
                name="netbox_proxbox_proxmoxnode_unique_endpoint_name",
            )
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.endpoint})"

    def get_absolute_url(self) -> str:
        """Plugin UI URL for this Proxmox node detail view."""
        return reverse("plugins:netbox_proxbox:proxmoxnode", args=[self.pk])

    @property
    def memory_usage_percent(self) -> float | None:
        """Calculate memory usage percentage."""
        if self.memory_usage is not None and self.max_memory:
            return (self.memory_usage / self.max_memory) * 100
        return None

    @property
    def cpu_usage_percent(self) -> float | None:
        """Return CPU usage as percentage (already stored as %)."""
        return self.cpu_usage
