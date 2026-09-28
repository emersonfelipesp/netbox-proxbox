"""Clarify that custom_fields_request_delay is compatibility-only."""

from decimal import Decimal

from django.db import migrations, models


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
    ]
