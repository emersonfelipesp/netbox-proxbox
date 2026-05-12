"""Create the ProxmoxVMCloudInit table for issue #363."""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0042_tenant_name_regex"),
        ("virtualization", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProxmoxVMCloudInit",
            fields=[
                (
                    "custom_field_data",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        help_text="Custom field data stored as JSON.",
                        null=True,
                    ),
                ),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("last_updated", models.DateTimeField(auto_now=True, null=True)),
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False
                    ),
                ),
                (
                    "ciuser",
                    models.CharField(
                        blank=True,
                        help_text="Proxmox cloud-init user (``ciuser``).",
                        max_length=64,
                    ),
                ),
                (
                    "sshkeys",
                    models.TextField(
                        blank=True,
                        help_text=(
                            "Decoded cloud-init SSH key bundle (one key per line). "
                            "Proxmox-side is URL-encoded; proxbox-api runs "
                            "urllib.parse.unquote before writing this row."
                        ),
                    ),
                ),
                (
                    "ipconfig0",
                    models.CharField(
                        blank=True,
                        help_text=(
                            "Cloud-init first-NIC IP configuration string from "
                            "Proxmox (e.g. ``ip=dhcp`` or "
                            "``ip=10.0.0.5/24,gw=10.0.0.1``)."
                        ),
                        max_length=255,
                    ),
                ),
                (
                    "sshkeys_truncated",
                    models.BooleanField(
                        default=False,
                        help_text=(
                            "True when proxbox-api truncated the ``sshkeys`` "
                            "payload because the decoded blob exceeded 10 KB."
                        ),
                    ),
                ),
                (
                    "last_synced",
                    models.DateTimeField(
                        auto_now=True,
                        help_text="Time of the last cloud-init reconciliation pass.",
                    ),
                ),
                (
                    "virtual_machine",
                    models.OneToOneField(
                        help_text="NetBox VM this cloud-init record reflects.",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="proxmox_cloudinit",
                        to="virtualization.virtualmachine",
                    ),
                ),
            ],
            options={
                "verbose_name": "Proxmox VM cloud-init",
                "verbose_name_plural": "Proxmox VM cloud-init records",
                "ordering": ("virtual_machine",),
            },
        ),
    ]
