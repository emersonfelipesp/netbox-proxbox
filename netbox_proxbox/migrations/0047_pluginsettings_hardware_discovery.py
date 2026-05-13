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
        ("netbox_proxbox", "0046_register_last_synced_role_cf"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                _add_column(TABLE, "hardware_discovery_enabled", "boolean", "FALSE"),
            ],
            state_operations=[
                migrations.AddField(
                    model_name="proxboxpluginsettings",
                    name="hardware_discovery_enabled",
                    field=models.BooleanField(
                        default=False,
                        verbose_name="Enable SSH-based hardware discovery",
                        help_text=(
                            "Master flag for the SSH-driven hardware-discovery pass. When "
                            "enabled, proxbox-api opens a pinned-fingerprint SSH session to "
                            "each ProxmoxNode that has a stored NodeSSHCredential row, runs "
                            "dmidecode + ethtool + ip link under sudo -n, and reflects the "
                            "parsed chassis / NIC values onto the matching dcim.Device and "
                            "dcim.Interface custom fields. Off by default — flipping off "
                            "results in zero SSH sockets opened during sync."
                        ),
                    ),
                ),
            ],
        ),
    ]
