"""Add global and per-endpoint Proxmox node Device name templates."""

from django.db import migrations, models

import netbox_proxbox.validators

from ._idempotent_ops import add_field_idempotent


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0103_custom_fields_request_delay_help_text"),
    ]

    operations = [
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
    ]
