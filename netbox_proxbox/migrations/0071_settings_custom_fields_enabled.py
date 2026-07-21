from django.db import migrations, models

from netbox_proxbox.migrations._idempotent_ops import add_field_idempotent


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0070_proxmox_metrics_influxdb"),
    ]

    operations = [
        add_field_idempotent(
            "proxboxpluginsettings",
            "custom_fields_enabled",
            models.BooleanField(
                default=False,
                help_text=(
                    "Deprecated. When disabled (the default), Proxbox uses the "
                    "typed Proxbox sync-state models as the sole source of truth "
                    "for the Proxmox-to-NetBox linkage and does not write, read, "
                    "or reconcile the legacy reflection custom fields. Enable only "
                    "for a temporary transition; while enabled, proxbox-api still "
                    "writes and reads the custom fields and emits deprecation "
                    "warnings. The custom fields will be removed in a future "
                    "release."
                ),
                verbose_name="Enable legacy custom fields (deprecated)",
            ),
        ),
    ]
