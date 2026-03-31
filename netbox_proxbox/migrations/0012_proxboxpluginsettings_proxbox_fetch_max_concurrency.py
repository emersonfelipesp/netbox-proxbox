"""Add Proxmox fetch concurrency setting to plugin settings singleton."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0011_proxmoxstorage"),
    ]

    operations = [
        migrations.AddField(
            model_name="proxboxpluginsettings",
            name="proxbox_fetch_max_concurrency",
            field=models.PositiveSmallIntegerField(
                default=8,
                help_text=(
                    "Maximum number of parallel Proxmox fetch operations per sync "
                    "stage. Higher values can speed up multi-cluster discovery but "
                    "may increase load."
                ),
                verbose_name="Proxmox fetch max concurrency",
            ),
        ),
    ]
