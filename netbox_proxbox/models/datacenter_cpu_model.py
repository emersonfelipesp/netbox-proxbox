"""ProxmoxDatacenterCpuModel model."""

from __future__ import annotations

from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from netbox.models import NetBoxModel

from netbox_proxbox.choices import FirewallSyncStatusChoices


class ProxmoxDatacenterCpuModel(NetBoxModel):
    """Custom CPU model defined at the Proxmox datacenter level."""

    endpoint = models.ForeignKey(
        to="netbox_proxbox.ProxmoxEndpoint",
        on_delete=models.CASCADE,
        related_name="datacenter_cpu_models",
        null=True,
        blank=True,
        verbose_name=_("Proxmox endpoint"),
    )
    cluster_name = models.CharField(
        max_length=255, help_text=_("Proxmox cluster name.")
    )
    cputype = models.CharField(
        max_length=255, help_text=_("Custom CPU type identifier.")
    )
    base_cputype = models.CharField(
        max_length=255, blank=True, help_text=_("Base CPU type.")
    )
    flags = models.CharField(
        max_length=512, blank=True, help_text=_("CPU feature flags.")
    )
    vendor_id = models.CharField(
        max_length=255, blank=True, help_text=_("CPUID vendor ID string.")
    )
    level = models.IntegerField(null=True, blank=True, help_text=_("CPUID level."))
    description = models.TextField(blank=True)
    status = models.CharField(
        max_length=20,
        choices=FirewallSyncStatusChoices,
        default=FirewallSyncStatusChoices.ACTIVE,
    )
    raw_config = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = _("Datacenter CPU Model")
        verbose_name_plural = _("Datacenter CPU Models")
        ordering = ("endpoint", "cluster_name", "cputype")
        constraints = [
            models.UniqueConstraint(
                fields=["endpoint", "cluster_name", "cputype"],
                name="netbox_proxbox_datacentercpumodel_unique_endpoint_cluster_cputype",
            )
        ]

    def __str__(self):
        return f"{self.cluster_name} / {self.cputype}"

    def get_absolute_url(self):
        return reverse(
            "plugins:netbox_proxbox:proxmoxdatacentercpumodel", args=[self.pk]
        )
