"""Django migration for netbox_proxbox."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0022_squashed_populate_fastapi_tokens_to_convert_unique_together_to_constraints"),
    ]

    operations = [
        migrations.AddField(
            model_name="proxboxpluginsettings",
            name="encryption_key",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Base64-encoded or raw encryption key for proxbox-api credential encryption. If set, proxbox-api will use this key instead of PROXBOX_ENCRYPTION_KEY env var. Leave blank to use environment variable only.",
                max_length=255,
                verbose_name="Encryption key",
            ),
        ),
    ]
