"""Add the destructive orphan-VM cleanup setting.

Issue #367 adds backend support for deleting Proxbox-discovered VMs that were
not touched by the current full-update run. Keep the plugin-side toggle
default-off and DB-backed so proxbox-api can read it through the existing
runtime settings API while operators can still override with
``PROXBOX_DELETE_ORPHANS``.
"""

from django.db import migrations, models


TABLE = "netbox_proxbox_proxboxpluginsettings"


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0045_pluginsettings_branching_fields"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql=(
                        f'ALTER TABLE "{TABLE}" '
                        'ADD COLUMN IF NOT EXISTS "delete_orphans" boolean '
                        "NOT NULL DEFAULT FALSE;"
                    ),
                    reverse_sql=(
                        f'ALTER TABLE "{TABLE}" DROP COLUMN IF EXISTS "delete_orphans";'
                    ),
                ),
            ],
            state_operations=[
                migrations.AddField(
                    model_name="proxboxpluginsettings",
                    name="delete_orphans",
                    field=models.BooleanField(
                        default=False,
                        verbose_name="Delete orphan VMs",
                        help_text=(
                            "When enabled, full-update runs delete "
                            "Proxbox-discovered VMs that were not touched by "
                            "the current sync run. Review a dry-run preview "
                            "before enabling in production."
                        ),
                    ),
                ),
            ],
        ),
    ]
