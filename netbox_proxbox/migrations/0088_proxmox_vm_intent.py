"""Add the plugin-owned virtual-machine intent model."""

from __future__ import annotations

import django.db.models.deletion
import netbox.models.deletion
import taggit.managers
import utilities.json
from django.db import migrations, models

from netbox_proxbox.migrations._idempotent_ops import create_model_idempotent


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0087_remove_hardware_discovery_custom_fields"),
        ("virtualization", "0052_gfk_indexes"),
    ]

    operations = [
        create_model_idempotent(
            name="ProxmoxVMIntent",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False
                    ),
                ),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                (
                    "last_updated",
                    models.DateTimeField(auto_now=True, blank=True, null=True),
                ),
                (
                    "custom_field_data",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        encoder=utilities.json.CustomFieldJSONEncoder,
                    ),
                ),
                (
                    "target_node",
                    models.CharField(
                        blank=True,
                        help_text="Proxmox node that should host this virtual machine.",
                        max_length=255,
                    ),
                ),
                (
                    "target_storage",
                    models.CharField(
                        blank=True,
                        help_text="Proxmox storage used for new virtual-machine disks.",
                        max_length=255,
                    ),
                ),
                (
                    "iso",
                    models.CharField(
                        blank=True,
                        help_text=(
                            "Optional Proxmox volume ID of the install ISO. Empty "
                            "means no ISO is attached on create."
                        ),
                        max_length=255,
                    ),
                ),
                (
                    "template_vmid",
                    models.IntegerField(
                        blank=True,
                        help_text=(
                            "Source VMID to clone from when creating this VM. Mutually "
                            "exclusive with ISO-driven create; both empty means an "
                            "empty VM."
                        ),
                        null=True,
                    ),
                ),
                (
                    "swap",
                    models.IntegerField(
                        blank=True, help_text="LXC swap allocation in MiB.", null=True
                    ),
                ),
                (
                    "rootfs",
                    models.CharField(
                        blank=True,
                        help_text="LXC root filesystem volume specification.",
                        max_length=255,
                    ),
                ),
                (
                    "ostemplate",
                    models.CharField(
                        blank=True,
                        help_text="LXC operating-system template volume ID.",
                        max_length=255,
                    ),
                ),
                (
                    "cloud_init_user",
                    models.CharField(
                        blank=True,
                        help_text=(
                            "Default cloud-init username. Empty means inherit the "
                            "Proxmox default."
                        ),
                        max_length=255,
                    ),
                ),
                (
                    "cloud_init_ssh_keys",
                    models.TextField(
                        blank=True,
                        help_text="Newline-separated authorized SSH public keys.",
                    ),
                ),
                (
                    "cloud_init_user_data",
                    models.TextField(
                        blank=True,
                        help_text="Optional raw cloud-init user-data YAML.",
                    ),
                ),
                (
                    "cloud_init_network",
                    models.TextField(
                        blank=True,
                        help_text="Optional cloud-init network configuration JSON.",
                    ),
                ),
                (
                    "intent_state",
                    models.CharField(
                        blank=True,
                        editable=False,
                        help_text="Last terminal intent verdict written by the apply job.",
                        max_length=64,
                    ),
                ),
                (
                    "last_apply_run_id",
                    models.CharField(
                        blank=True,
                        editable=False,
                        help_text="Most recent apply-run UUID written by the apply job.",
                        max_length=255,
                    ),
                ),
                (
                    "virtual_machine",
                    models.OneToOneField(
                        help_text=(
                            "NetBox virtual machine governed by this Proxmox intent."
                        ),
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="proxbox_intent",
                        to="virtualization.virtualmachine",
                    ),
                ),
                (
                    "tags",
                    taggit.managers.TaggableManager(
                        through="extras.TaggedItem", to="extras.Tag"
                    ),
                ),
            ],
            options={
                "ordering": ("virtual_machine",),
                "verbose_name": "Proxmox VM intent",
                "verbose_name_plural": "Proxmox VM intents",
            },
            bases=(netbox.models.deletion.DeleteMixin, models.Model),
        ),
    ]
