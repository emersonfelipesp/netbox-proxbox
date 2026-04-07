"""Define synchronized Proxmox storage inventory rows."""

from django.db import models
from django.urls import reverse

from netbox.models import NetBoxModel


class ProxmoxStorageVirtualDisk(models.Model):
    """Link a NetBox VirtualDisk to a ProxmoxStorage row."""

    proxmox_storage = models.ForeignKey(
        to="netbox_proxbox.ProxmoxStorage",
        on_delete=models.CASCADE,
        related_name="virtual_disk_links",
    )
    virtual_disk = models.ForeignKey(
        to="virtualization.VirtualDisk",
        on_delete=models.CASCADE,
        related_name="proxmox_storage_links",
    )

    class Meta:
        unique_together = ("proxmox_storage", "virtual_disk")

    def __str__(self) -> str:
        return f"{self.proxmox_storage} - {self.virtual_disk}"


class ProxmoxStorage(NetBoxModel):
    """Storage definition synced from Proxmox clusters."""

    cluster = models.ForeignKey(
        to="virtualization.Cluster",
        on_delete=models.CASCADE,
        related_name="proxmox_storages",
    )
    name = models.CharField(max_length=255)
    storage_type = models.CharField(max_length=100, null=True, blank=True)
    content = models.CharField(max_length=255, null=True, blank=True)
    path = models.CharField(max_length=255, null=True, blank=True)
    nodes = models.CharField(max_length=255, null=True, blank=True)
    shared = models.BooleanField(default=False)
    enabled = models.BooleanField(default=True)
    virtual_disks = models.ManyToManyField(
        to="virtualization.VirtualDisk",
        related_name="proxmox_storages",
        blank=True,
        through="netbox_proxbox.ProxmoxStorageVirtualDisk",
    )

    class Meta:
        ordering = ("cluster__name", "name")
        unique_together = ("cluster", "name")
        verbose_name = "Proxmox Storage"
        verbose_name_plural = "Proxmox Storages"

    def __str__(self) -> str:
        """Cluster-qualified storage label for list displays."""
        return f"{self.cluster.name}/{self.name}"

    def get_absolute_url(self) -> str:
        """Plugin UI URL for this storage row."""
        return reverse("plugins:netbox_proxbox:proxmoxstorage", args=[self.pk])
