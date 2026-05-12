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
                _add_column(TABLE, "parse_description_metadata", "boolean", "FALSE"),
            ],
            state_operations=[
                migrations.AddField(
                    model_name="proxboxpluginsettings",
                    name="parse_description_metadata",
                    field=models.BooleanField(
                        default=False,
                        verbose_name="Parse description metadata",
                        help_text=(
                            "When enabled, proxbox-api reads each Proxmox object's "
                            "description for a fenced ``netbox-metadata`` JSON block "
                            "and applies the parsed PK ids to the matching NetBox "
                            "fields. Per-field ``overwrite_*`` flags still gate keys "
                            "they cover. Disabled by default."
                        ),
                    ),
                ),
            ],
        ),
    ]
