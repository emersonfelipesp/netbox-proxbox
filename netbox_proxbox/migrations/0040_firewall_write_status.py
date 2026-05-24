from django.db import migrations, models

from netbox_proxbox.migrations._idempotent_ops import add_field_idempotent


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0039_squashed_0039_0042_pve_9_2_firewall_sdn"),
    ]

    operations = [
        add_field_idempotent(
            model_name="proxmoxfirewalloptions",
            field_name="status",
            field=models.CharField(
                choices=[
                    ("active", "Active"),
                    ("stale", "Stale"),
                    ("error", "Error"),
                ],
                default="active",
                max_length=20,
            ),
        ),
    ]
