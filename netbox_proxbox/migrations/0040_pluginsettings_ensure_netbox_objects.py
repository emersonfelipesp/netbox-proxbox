from django.db import migrations, models


def _add_column(table: str, column: str, sql_type: str, default: str) -> migrations.RunSQL:
    return migrations.RunSQL(
        sql=(
            f'ALTER TABLE "{table}" '
            f'ADD COLUMN IF NOT EXISTS "{column}" {sql_type} NOT NULL DEFAULT {default};'
        ),
        reverse_sql=(
            f'ALTER TABLE "{table}" DROP COLUMN IF EXISTS "{column}";'
        ),
    )


TABLE = "netbox_proxbox_proxboxpluginsettings"


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0039_pluginsettings_overwrite_ip_address_dns_name"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                _add_column(TABLE, "ensure_netbox_objects", "boolean", "TRUE"),
            ],
            state_operations=[
                migrations.AddField(
                    model_name="proxboxpluginsettings",
                    name="ensure_netbox_objects",
                    field=models.BooleanField(
                        default=True,
                        verbose_name="Ensure NetBox supporting objects on startup",
                        help_text=(
                            "When enabled, proxbox-api runs an idempotent NetBox-side "
                            "bootstrap pass on each process startup that ensures the "
                            "supporting objects the plugin requires (cluster type, "
                            "device roles, manufacturer, device type, VM type, "
                            "custom fields, discovery tags) exist. Disable to leave "
                            "hand-curated NetBox installs untouched."
                        ),
                    ),
                ),
            ],
        ),
    ]
