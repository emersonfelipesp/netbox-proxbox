"""Add ``allow_writes`` to ProxmoxEndpoint — per-endpoint gate for operational verbs.

Issue #376: operational verbs (start, stop, snapshot, migrate) are dispatched
through ``proxbox-api`` to a Proxmox cluster only when the target endpoint has
``allow_writes=True``. Default off — enabling this widens the trust boundary
and must be paired with the new ``core.run_proxmox_action`` permission.

See ``docs/design/operational-verbs.md`` for the full contract.
"""

from django.db import migrations, models


TABLE = "netbox_proxbox_proxmoxendpoint"


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0039_pluginsettings_overwrite_ip_address_dns_name"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql=(
                        f'ALTER TABLE "{TABLE}" '
                        'ADD COLUMN IF NOT EXISTS "allow_writes" boolean NOT NULL DEFAULT FALSE;'
                    ),
                    reverse_sql=(
                        f'ALTER TABLE "{TABLE}" DROP COLUMN IF EXISTS "allow_writes";'
                    ),
                ),
            ],
            state_operations=[
                migrations.AddField(
                    model_name="proxmoxendpoint",
                    name="allow_writes",
                    field=models.BooleanField(
                        default=False,
                        verbose_name="Allow Proxmox-side writes",
                        help_text=(
                            "When enabled, operational verbs (start, stop, snapshot, "
                            "migrate) may be dispatched against this endpoint. Default "
                            "off. Enabling this widens the trust boundary; restrict the "
                            "new core.run_proxmox_action permission to a small operator "
                            "group."
                        ),
                    ),
                ),
            ],
        ),
    ]
