from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0039_squashed_0039_0042_pve_9_2_firewall_sdn"),
    ]

    operations = [
        migrations.AddField(
            model_name="proxmoxfirewalloptions",
            name="status",
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
