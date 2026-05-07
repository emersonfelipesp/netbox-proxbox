from django.db import migrations, models


SETTINGS_TABLE = "netbox_proxbox_proxboxpluginsettings"
ENDPOINT_TABLE = "netbox_proxbox_proxmoxendpoint"
FIELD = "overwrite_ip_address_dns_name"


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0038_fastapiendpoint_use_https"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql=(
                        f'ALTER TABLE "{SETTINGS_TABLE}" '
                        f'ADD COLUMN IF NOT EXISTS "{FIELD}" boolean NOT NULL DEFAULT TRUE;'
                    ),
                    reverse_sql=(
                        f'ALTER TABLE "{SETTINGS_TABLE}" DROP COLUMN IF EXISTS "{FIELD}";'
                    ),
                ),
                migrations.RunSQL(
                    sql=(
                        f'ALTER TABLE "{ENDPOINT_TABLE}" '
                        f'ADD COLUMN IF NOT EXISTS "{FIELD}" boolean NULL;'
                    ),
                    reverse_sql=(
                        f'ALTER TABLE "{ENDPOINT_TABLE}" DROP COLUMN IF EXISTS "{FIELD}";'
                    ),
                ),
            ],
            state_operations=[
                migrations.AddField(
                    model_name="proxboxpluginsettings",
                    name=FIELD,
                    field=models.BooleanField(
                        default=True,
                        verbose_name="Overwrite IP address DNS name",
                        help_text=(
                            "When disabled, sync never changes the dns_name field on existing IP "
                            "addresses; dns_name is still populated when an IP is created."
                        ),
                    ),
                ),
                migrations.AddField(
                    model_name="proxmoxendpoint",
                    name=FIELD,
                    field=models.BooleanField(
                        blank=True,
                        null=True,
                        verbose_name="Overwrite IP address DNS name",
                        help_text=(
                            "Per-endpoint override for the global Proxbox setting. Leave blank to inherit."
                        ),
                    ),
                ),
            ],
        ),
    ]
