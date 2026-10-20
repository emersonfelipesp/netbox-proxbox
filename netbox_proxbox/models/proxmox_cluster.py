"""Proxmox cluster tracking and linkage to NetBox virtualization.Cluster."""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.urls import NoReverseMatch, reverse
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
        try:
            return reverse("plugins:netbox_proxbox:proxmoxcluster", args=[self.pk])
        except NoReverseMatch:
            return ""

    def _validate_existing_identity(self, previous) -> None:
        if previous is None:
            return
        if previous.endpoint_id != self.endpoint_id:
            raise ValidationError(
                {"endpoint": "An existing tracking row cannot change endpoints."}
            )
        if previous.netbox_cluster_id and self.netbox_cluster_id not in (
            None,
            previous.netbox_cluster_id,
        ):
            raise ValidationError(
                {
                    "netbox_cluster": "Clear an obsolete tracking link explicitly before replacing it."
                }
            )

    def _validate_claim_authority(self, previous) -> None:
        from netbox_proxbox.services.cluster_binding_authority import (
            cluster_binding_write_allowed,
        )

        previous_id = getattr(previous, "netbox_cluster_id", None)
        if self.netbox_cluster_id is None or self.netbox_cluster_id == previous_id:
            return
        if not cluster_binding_write_allowed(self.netbox_cluster_id, self.endpoint_id):
            raise ValidationError(
                {
                    "netbox_cluster": "Native cluster claims require the protected synchronization action."
                }
            )

    def _validate_binding(self, endpoint) -> None:
        """Refuse implicit ownership transfer through supported tracking writes."""
        previous = type(self).objects.filter(pk=self.pk).first() if self.pk else None
        self._validate_existing_identity(previous)
        self._validate_claim_authority(previous)
        if self.netbox_cluster_id is None:
            return
        if endpoint.netbox_cluster_id not in (None, self.netbox_cluster_id):
            raise ValidationError(
                {
                    "netbox_cluster": "The endpoint already owns a different native cluster."
                }
            )
        if (
            type(endpoint)
            .objects.filter(netbox_cluster_id=self.netbox_cluster_id)
            .exclude(pk=endpoint.pk)
            .exists()
        ):
            raise ValidationError(
                {"netbox_cluster": "Another endpoint owns this native cluster."}
            )
        self._validate_other_claims(endpoint)

    def _validate_other_claims(self, endpoint) -> None:
        claims = (
            type(self)
            .objects.exclude(pk=self.pk)
            .filter(netbox_cluster_id__isnull=False)
        )
        if (
            claims.filter(endpoint=endpoint)
            .exclude(netbox_cluster_id=self.netbox_cluster_id)
            .exists()
        ):
            raise ValidationError(
                {
                    "netbox_cluster": "Resolve this endpoint's conflicting tracking links first."
                }
            )
        if (
            claims.filter(netbox_cluster_id=self.netbox_cluster_id)
            .exclude(endpoint=endpoint)
            .exists()
        ):
            raise ValidationError(
                {
                    "netbox_cluster": "Another endpoint's tracking row claims this native cluster."
                }
            )

    def clean(self) -> None:
        super().clean()
        if self.endpoint_id:
            self._validate_binding(self.endpoint)

    def save(self, *args, **kwargs) -> None:
        """Serialize tracking claims with endpoint synchronization and native deletion."""
        from virtualization.models import Cluster
        from netbox_proxbox.models.proxmox_endpoint import ProxmoxEndpoint

        with transaction.atomic():
            endpoint = ProxmoxEndpoint.objects.select_for_update().get(
                pk=self.endpoint_id
            )
            if self.netbox_cluster_id:
                Cluster.objects.select_for_update().get(pk=self.netbox_cluster_id)
            self._validate_binding(endpoint)
            super().save(*args, **kwargs)
