"""Define synchronized Proxmox storage inventory rows."""

from django.db import models
from django.urls import reverse

from netbox.models import NetBoxModel


class ProxmoxStorage(NetBoxModel):
    """Storage definition synced from Proxmox clusters."""

    cluster = models.CharField(max_length=255)
    name = models.CharField(max_length=255)
    storage_type = models.CharField(max_length=100, null=True, blank=True)
    content = models.CharField(max_length=255, null=True, blank=True)
    path = models.CharField(max_length=255, null=True, blank=True)
    nodes = models.CharField(max_length=255, null=True, blank=True)
    shared = models.BooleanField(default=False)
    enabled = models.BooleanField(default=True)

    class Meta:
        ordering = ("cluster", "name")
        unique_together = ("cluster", "name")
        verbose_name = "Proxmox Storage"
        verbose_name_plural = "Proxmox Storages"

    def __str__(self):
        """Cluster-qualified storage label for list displays."""
        return f"{self.cluster}/{self.name}"

    def get_absolute_url(self):
        """Plugin UI URL for this storage row."""
        return reverse("plugins:netbox_proxbox:proxmoxstorage", args=[self.pk])
