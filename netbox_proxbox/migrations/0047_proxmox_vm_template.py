"""Add ProxmoxVMTemplate model for dedicated Proxmox VM template inventory."""

from __future__ import annotations

import django.db.models.deletion
import taggit.managers
from django.db import migrations, models

from netbox_proxbox.migrations._idempotent_ops import create_model_idempotent


class Migration(migrations.Migration):
    dependencies = [
        ("extras", "0134_owner"),
        ("netbox_proxbox", "0046_sync_modes"),
        ("virtualization", "0052_gfk_indexes"),
    ]

    operations = [
        create_model_idempotent(
            name="ProxmoxVMTemplate",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False
                    ),
                ),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("last_updated", models.DateTimeField(auto_now=True, null=True)),
                (
                    "custom_field_data",
                    models.JSONField(blank=True, default=dict, encoder=None),
                ),
                ("name", models.CharField(max_length=255, verbose_name="Name")),
                ("vmid", models.PositiveIntegerField(verbose_name="VMID")),
                (
                    "node_name",
                    models.CharField(
                        blank=True, max_length=255, verbose_name="Node name"
                    ),
                ),
                (
                    "proxmox_type",
                    models.CharField(
                        default="qemu", max_length=10, verbose_name="Proxmox type"
                    ),
                ),
                (
                    "status",
                    models.CharField(blank=True, max_length=50, verbose_name="Status"),
                ),
                (
                    "vcpus",
                    models.PositiveSmallIntegerField(
                        blank=True, null=True, verbose_name="vCPUs"
                    ),
                ),
                (
                    "memory",
                    models.PositiveIntegerField(
                        blank=True, null=True, verbose_name="Memory (MB)"
                    ),
                ),
                (
                    "disk",
                    models.PositiveIntegerField(
                        blank=True, null=True, verbose_name="Disk (GB)"
                    ),
                ),
                (
                    "os_type",
                    models.CharField(
                        blank=True, max_length=50, verbose_name="OS type"
                    ),
                ),
                (
                    "description",
                    models.TextField(blank=True, verbose_name="Description"),
                ),
                (
                    "cloud_init_enabled",
                    models.BooleanField(
                        default=False, verbose_name="Cloud-init enabled"
                    ),
                ),
                (
                    "net_config",
                    models.JSONField(
                        blank=True, default=dict, verbose_name="Network config"
                    ),
                ),
                (
                    "disk_config",
                    models.JSONField(
                        blank=True, default=dict, verbose_name="Disk config"
                    ),
                ),
                (
                    "raw_config",
                    models.JSONField(
                        blank=True, default=dict, verbose_name="Raw config"
                    ),
                ),
                (
                    "last_synced",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="Last synced"
                    ),
                ),
                (
                    "tags",
                    taggit.managers.TaggableManager(
                        through="extras.TaggedItem",
                        to="extras.Tag",
                        help_text="A comma-separated list of tags.",
                        verbose_name="Tags",
                    ),
                ),
                # Required FK
                (
                    "proxmox_endpoint",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="vm_templates",
                        to="netbox_proxbox.proxmoxendpoint",
                        verbose_name="Proxmox endpoint",
                    ),
                ),
                # Optional FKs (all nullable)
                (
                    "cluster",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="vm_templates",
                        to="netbox_proxbox.proxmoxcluster",
                        verbose_name="Proxmox cluster",
                    ),
                ),
                (
                    "node",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="vm_templates",
                        to="netbox_proxbox.proxmoxnode",
                        verbose_name="Proxmox node",
                    ),
                ),
                (
                    "source_vm",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="derived_templates",
                        to="virtualization.virtualmachine",
                        verbose_name="Source VM",
                    ),
                ),
                (
                    "cloned_vms",
                    models.ManyToManyField(
                        blank=True,
                        related_name="source_template",
                        to="virtualization.virtualmachine",
                        verbose_name="Cloned VMs",
                    ),
                ),
            ],
            options={
                "verbose_name": "Proxmox VM Template",
                "verbose_name_plural": "Proxmox VM Templates",
                "ordering": ["name", "vmid"],
                "unique_together": {("proxmox_endpoint", "vmid")},
            },
        ),
    ]
