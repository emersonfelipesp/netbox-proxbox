"""Add release settings and clarify compatibility-only delay help."""

from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models

import netbox_proxbox.validators

from ._idempotent_ops import add_field_idempotent


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0102_vm_cloudinit_openbao_references"),
    ]

    operations = [
        migrations.AlterField(
            model_name="proxboxpluginsettings",
            name="custom_fields_request_delay",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                help_text=(
                    "Reserved for compatibility. This value is stored and exposed on the "
                    "Plugin Settings API, but netbox-proxbox and proxbox-api do not read it; "
                    "changing it has no effect on sync behavior."
                ),
                max_digits=5,
                verbose_name="Custom fields request delay (seconds)",
            ),
        ),
        add_field_idempotent(
            "proxboxpluginsettings",
            "node_device_name_template",
            models.CharField(
                default="{node}",
                help_text=(
                    "Template for synchronized Proxmox node Device names. Supported "
                    "placeholders: {node}, {cluster}, {cluster_slug}, and {endpoint}."
                ),
                max_length=128,
                validators=[
                    netbox_proxbox.validators.validate_node_device_name_template
                ],
                verbose_name="Node device name template",
            ),
        ),
        add_field_idempotent(
            "proxmoxendpoint",
            "node_device_name_template",
            models.CharField(
                blank=True,
                default="",
                help_text=(
                    "Optional per-endpoint override for NetBox node Device names. "
                    "Leave blank to inherit the global template."
                ),
                max_length=128,
                validators=[
                    netbox_proxbox.validators.validate_node_device_name_template
                ],
                verbose_name="Node device name template",
            ),
        ),
        add_field_idempotent(
            "proxboxpluginsettings",
            "sync_job_timeout",
            models.PositiveIntegerField(
                default=7200,
                help_text=(
                    "RQ wall-clock limit for a complete Proxbox synchronization job. "
                    "Increase this for large estates whose valid syncs exceed two hours. "
                    "Changes apply only to jobs enqueued after the setting is saved."
                ),
                validators=[MinValueValidator(3600), MaxValueValidator(604800)],
                verbose_name="Synchronization job timeout (seconds)",
            ),
        ),
    ]
