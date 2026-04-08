"""Add backend log file path setting to ProxboxPluginSettings."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0023_add_ssrf_settings"),
    ]

    operations = [
        migrations.AddField(
            model_name="proxboxpluginsettings",
            name="backend_log_file_path",
            field=models.CharField(
                default="/var/log/proxbox.log",
                help_text=(
                    "Absolute file path for proxbox-api rotated log archive output "
                    "(for example /var/log/proxbox.log). Changes apply after proxbox-api restart."
                ),
                max_length=255,
                verbose_name="Backend log file path",
            ),
        ),
    ]
