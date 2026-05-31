"""Dedicated model for Proxmox VM templates, separate from VirtualMachine."""

from __future__ import annotations

from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from netbox.models import NetBoxModel


class ProxmoxVMTemplate(NetBoxModel):
    """
    Stores a Proxmox VM template (QEMU or LXC) as a dedicated NetBox object.

    Templates are build artifacts (golden images) rather than running workloads
    and must not be stored as VirtualMachine rows. This model captures the full
    Proxmox configuration snapshot and optionally links back to derived NetBox
    VirtualMachine objects that were cloned from this template.

    Sync behaviour is governed by the ``sync_mode_vm_template`` setting on the
    active ProxmoxEndpoint or the global ProxboxPluginSettings singleton.
    """

    # ------------------------------------------------------------------
    # Required identity fields
    # ------------------------------------------------------------------
    name = models.CharField(
        max_length=255,
        verbose_name=_("Name"),
        help_text=_("Proxmox VM template name as reported by the API."),
    )
    vmid = models.PositiveIntegerField(
        verbose_name=_("VMID"),
        help_text=_("Proxmox VM ID (unique per endpoint)."),
    )
    proxmox_endpoint = models.ForeignKey(
        to="netbox_proxbox.ProxmoxEndpoint",
        on_delete=models.CASCADE,
        related_name="vm_templates",
        verbose_name=_("Proxmox endpoint"),
        help_text=_("ProxmoxEndpoint this template was discovered on."),
    )

    # ------------------------------------------------------------------
    # Optional proxbox relationships
    # ------------------------------------------------------------------
    cluster = models.ForeignKey(
        to="netbox_proxbox.ProxmoxCluster",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="vm_templates",
        verbose_name=_("Proxmox cluster"),
        help_text=_("Proxmox cluster this template belongs to (optional)."),
    )
    node = models.ForeignKey(
        to="netbox_proxbox.ProxmoxNode",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="vm_templates",
        verbose_name=_("Proxmox node"),
        help_text=_("Proxmox node (DCIM Device) hosting the template (optional)."),
    )

    # ------------------------------------------------------------------
    # Optional NetBox core relationships (all nullable)
    # ------------------------------------------------------------------
    source_vm = models.ForeignKey(
        to="virtualization.VirtualMachine",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="derived_templates",
        verbose_name=_("Source VM"),
        help_text=_(
            "The NetBox VirtualMachine from which this template was originally "
            "created (optional)."
        ),
    )
    cloned_vms = models.ManyToManyField(
        to="virtualization.VirtualMachine",
        blank=True,
        related_name="source_template",
        verbose_name=_("Cloned VMs"),
        help_text=_(
            "NetBox VirtualMachine objects that were cloned from this template "
            "(optional, many-to-many)."
        ),
    )

    # ------------------------------------------------------------------
    # Proxmox config fields
    # ------------------------------------------------------------------
    node_name = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_("Node name"),
        help_text=_("Proxmox node name string (e.g. 'pve01')."),
    )
    proxmox_type = models.CharField(
        max_length=10,
        default="qemu",
        verbose_name=_("Proxmox type"),
        help_text=_("Guest type: 'qemu' (QEMU/KVM) or 'lxc' (container)."),
    )
    status = models.CharField(
        max_length=50,
        blank=True,
        verbose_name=_("Status"),
        help_text=_("Proxmox resource status (e.g. 'stopped', 'running')."),
    )
    vcpus = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name=_("vCPUs"),
        help_text=_("Number of virtual CPUs."),
    )
    memory = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Memory (MB)"),
        help_text=_("Allocated memory in megabytes."),
    )
    disk = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Disk (GB)"),
        help_text=_("Total disk allocation in gigabytes."),
    )
    os_type = models.CharField(
        max_length=50,
        blank=True,
        verbose_name=_("OS type"),
        help_text=_("Proxmox guest OS type identifier (e.g. 'l26', 'win10')."),
    )
    description = models.TextField(
        blank=True,
        verbose_name=_("Description"),
        help_text=_("Free-text description from Proxmox or operator."),
    )
    cloud_init_enabled = models.BooleanField(
        default=False,
        verbose_name=_("Cloud-init enabled"),
        help_text=_("Whether this template uses a cloud-init drive."),
    )

    # ------------------------------------------------------------------
    # Raw config snapshots (JSON blobs)
    # ------------------------------------------------------------------
    net_config = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("Network config"),
        help_text=_("Raw Proxmox network interface config (net0, net1, …)."),
    )
    disk_config = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("Disk config"),
        help_text=_("Raw Proxmox disk configuration entries."),
    )
    raw_config = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("Raw config"),
        help_text=_("Full Proxmox API config dump for this template."),
    )

    # ------------------------------------------------------------------
    # Sync tracking
    # ------------------------------------------------------------------
    last_synced = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Last synced"),
        help_text=_("Timestamp of the last successful sync from Proxmox."),
    )

    class Meta:
        ordering = ["name", "vmid"]
        unique_together = [("proxmox_endpoint", "vmid")]
        verbose_name = _("Proxmox VM Template")
        verbose_name_plural = _("Proxmox VM Templates")

    def __str__(self) -> str:
        return f"{self.name} (vmid={self.vmid})"

    def get_absolute_url(self) -> str:
        return reverse("plugins:netbox_proxbox:proxmoxvmtemplate", args=[self.pk])
