"""Allow storage membership to retain every node reported by Proxmox."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0078_sync_state_last_synced_role"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql=(
                        'ALTER TABLE "netbox_proxbox_proxmoxstorage" '
                        'ALTER COLUMN "nodes" TYPE text'
                    ),
                    # Expand-only rollback: after a value longer than 255
                    # characters exists, narrowing the PostgreSQL column would
                    # fail or require destructive truncation. Django's historical
                    # state still rolls back to CharField while the compatible
                    # text column remains in place.
                    reverse_sql=migrations.RunSQL.noop,
                ),
            ],
            state_operations=[
                migrations.AlterField(
                    model_name="proxmoxstorage",
                    name="nodes",
                    field=models.TextField(
                        blank=True,
                        help_text=(
                            "Comma-separated Proxmox node membership without a "
                            "length limit."
                        ),
                        null=True,
                    ),
                ),
            ],
        ),
    ]
