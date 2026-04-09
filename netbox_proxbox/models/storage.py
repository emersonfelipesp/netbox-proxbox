"""Define synchronized Proxmox storage inventory rows."""

from __future__ import annotations

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
        constraints = [
            models.UniqueConstraint(
                fields=("proxmox_storage", "virtual_disk"),
                name="unique_proxmox_storage_virtual_disk",
            ),
        ]

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

    # Remote-host fields (NFS, CIFS, PBS, iSCSI, ESXi, Ceph)
    server = models.CharField(max_length=255, null=True, blank=True)
    port = models.PositiveIntegerField(null=True, blank=True)
    username = models.CharField(max_length=255, null=True, blank=True)

    # NFS / CIFS
    export = models.CharField(max_length=255, null=True, blank=True)
    share = models.CharField(max_length=255, null=True, blank=True)

    # Ceph / RBD
    pool = models.CharField(max_length=255, null=True, blank=True)
    monhost = models.CharField(max_length=512, null=True, blank=True)
    namespace = models.CharField(max_length=255, null=True, blank=True)

    # PBS
    datastore = models.CharField(max_length=255, null=True, blank=True)
    subdir = models.CharField(max_length=255, null=True, blank=True)

    # Filesystem
    mountpoint = models.CharField(max_length=255, null=True, blank=True)
    is_mountpoint = models.CharField(max_length=255, null=True, blank=True)
    preallocation = models.CharField(max_length=50, null=True, blank=True)
    format = models.CharField(max_length=100, null=True, blank=True)

    # Retention / backup
    prune_backups = models.CharField(max_length=512, null=True, blank=True)
    max_protected_backups = models.IntegerField(null=True, blank=True)

    # Full raw config from Proxmox API
    raw_config = models.JSONField(
        default=dict,
        blank=True,
        help_text="Full raw configuration returned by the Proxmox storage API.",
    )

    virtual_disks = models.ManyToManyField(
        to="virtualization.VirtualDisk",
        related_name="proxmox_storages",
        blank=True,
        through="netbox_proxbox.ProxmoxStorageVirtualDisk",
    )

    class Meta:
        ordering = ("cluster__name", "name")
        constraints = [
            models.UniqueConstraint(
                fields=("cluster", "name"),
                name="unique_proxmox_storage_cluster_name",
            ),
        ]
        verbose_name = "Proxmox Storage"
        verbose_name_plural = "Proxmox Storages"

    def __str__(self) -> str:
        """Cluster-qualified storage label for list displays."""
        return f"{self.cluster.name}/{self.name}"

    def get_absolute_url(self) -> str:
        """Plugin UI URL for this storage row."""
        return reverse("plugins:netbox_proxbox:proxmoxstorage", args=[self.pk])
