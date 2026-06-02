"""Add interface batch size and delay settings for large VM sync."""

from django.db import migrations, models

from netbox_proxbox.migrations._idempotent_ops import add_field_idempotent


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0047_proxmox_vm_template"),
    ]

    operations = [
        add_field_idempotent(
            model_name="proxboxpluginsettings",
            field_name="interface_batch_size",
            field=models.PositiveSmallIntegerField(
                default=5,
                help_text=(
                    "Number of VM interfaces (and their IP addresses, subnets, VLANs) synced "
                    "per batch. Large VMs (50+ interfaces) may timeout if synced all at once; "
                    "batching prevents overwhelming NetBox with concurrent API calls."
                ),
                verbose_name="Interface batch size",
            ),
        ),
        add_field_idempotent(
            model_name="proxboxpluginsettings",
            field_name="interface_batch_delay_ms",
            field=models.PositiveIntegerField(
                default=100,
                help_text=(
                    "Milliseconds to wait between interface batches to throttle NetBox load."
                ),
                verbose_name="Interface batch delay (ms)",
            ),
        ),
    ]
