from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0104_node_device_name_template"),
    ]

    operations = [
        migrations.AddField(
            model_name="proxboxpluginsettings",
            name="sync_job_timeout",
            field=models.PositiveIntegerField(
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
