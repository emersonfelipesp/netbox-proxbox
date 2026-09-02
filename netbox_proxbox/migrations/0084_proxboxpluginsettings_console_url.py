from django.db import migrations, models

from netbox_proxbox.migrations._idempotent_ops import add_field_idempotent


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0083_openbao_credential_storage"),
    ]

    operations = [
        add_field_idempotent(
            "proxboxpluginsettings",
            "console_url",
            models.URLField(blank=True, default="", verbose_name="Browser console URL"),
        ),
    ]
