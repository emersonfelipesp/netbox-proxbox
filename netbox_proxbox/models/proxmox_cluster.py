"""Proxmox cluster tracking and linkage to NetBox virtualization.Cluster."""

from __future__ import annotations

from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from netbox.models import NetBoxModel

from netbox_proxbox.choices import ProxmoxModeChoices


class ProxmoxCluster(NetBoxModel):
    """
    Tracks Proxmox cluster information synced from a ProxmoxEndpoint.
    Links to NetBox's native virtualization.Cluster for integration.
    """

    endpoint = models.ForeignKey(
        to="netbox_proxbox.ProxmoxEndpoint",
        on_delete=models.CASCADE,
        related_name="proxmox_clusters",
        verbose_name=_("Proxmox endpoint"),
        help_text=_("ProxmoxEndpoint this cluster is discovered from."),
    )
    netbox_cluster = models.ForeignKey(
        to="virtualization.Cluster",
        on_delete=models.SET_NULL,
        related_name="proxmox_cluster_tracking",
        verbose_name=_("NetBox cluster"),
        null=True,
        blank=True,
        help_text=_("Linked NetBox cluster object created during device sync."),
    )
    name = models.CharField(
        max_length=255,
        verbose_name=_("Cluster name"),
        help_text=_("Proxmox cluster name as reported by the API."),
    )
    cluster_id = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_("Cluster ID"),
        help_text=_("Proxmox cluster ID."),
    )
    mode = models.CharField(
        max_length=255,
        choices=ProxmoxModeChoices,
        default=ProxmoxModeChoices.PROXMOX_MODE_CLUSTER,
        verbose_name=_("Mode"),
        help_text=_("Cluster mode: standalone or cluster."),
    )
    nodes_count = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Nodes count"),
        help_text=_("Number of nodes in the cluster."),
    )
    quorate = models.BooleanField(
        default=False,
        verbose_name=_("Quorate"),
        help_text=_("Whether the cluster has quorum."),
    )
    version = models.IntegerField(
        null=True,
        blank=True,
        verbose_name=_("Corosync version"),
        help_text=_("Corosync configuration version."),
    )

    class Meta:
        ordering = ("endpoint", "name")
        verbose_name = _("Proxmox cluster")
        verbose_name_plural = _("Proxmox clusters")
        constraints = [
            models.UniqueConstraint(
                fields=["endpoint", "name"],
                name="netbox_proxbox_proxmoxcluster_unique_endpoint_name",
            )
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.endpoint})"

    def get_absolute_url(self) -> str:
        """Plugin UI URL for this Proxmox cluster detail view."""
        return reverse("plugins:netbox_proxbox:proxmoxcluster", args=[self.pk])
