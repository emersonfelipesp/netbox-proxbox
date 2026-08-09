from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0078_sync_state_last_synced_role"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="proxboxpluginsettings",
            options={
                "verbose_name": "Proxbox plugin settings",
                "verbose_name_plural": "Proxbox plugin settings",
                "permissions": (
                    (
                        "reset_encrypted_secrets",
                        "Can destructively reset Proxbox encrypted secrets",
                    ),
                ),
            },
        ),
    ]
