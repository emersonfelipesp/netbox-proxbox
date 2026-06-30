from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0055_sdn_sync_controls_and_inventory"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                # Add the column with the model default ("api") so the schema
                # matches ProxmoxAccessMethodChoices.API for future inserts.
                migrations.RunSQL(
                    sql=(
                        'ALTER TABLE "netbox_proxbox_proxmoxendpoint" '
                        'ADD COLUMN IF NOT EXISTS "access_methods" '
                        "varchar(16) NOT NULL DEFAULT 'api';"
                    ),
                    reverse_sql=(
                        'ALTER TABLE "netbox_proxbox_proxmoxendpoint" '
                        'DROP COLUMN IF EXISTS "access_methods";'
                    ),
                ),
                # Backfill PRE-EXISTING rows to "api_ssh" (NON-BREAKING): the SSH
                # terminal was previously ungated, so defaulting existing
                # endpoints to API-only would silently disable in-use SSH
                # terminals on upgrade. New rows still default to "api" via the
                # model/column default above; this UPDATE only touches rows that
                # exist at migration time.
                migrations.RunSQL(
                    sql=(
                        'UPDATE "netbox_proxbox_proxmoxendpoint" '
                        "SET \"access_methods\" = 'api_ssh';"
                    ),
                    reverse_sql=migrations.RunSQL.noop,
                ),
            ],
            state_operations=[
                migrations.AddField(
                    model_name="proxmoxendpoint",
                    name="access_methods",
                    field=models.CharField(
                        choices=[
                            ("api", "API only"),
                            ("api_ssh", "API + SSH"),
                        ],
                        default="api",
                        help_text=(
                            "Transport access method for this endpoint. 'API "
                            "only' permits Read+Write over the Proxmox HTTP API; "
                            "'API + SSH' additionally permits SSH (the browser "
                            "SSH terminal). SSH only complements API; there is "
                            "no SSH-only option. Orthogonal to 'Allow "
                            "Proxmox-side writes'. New endpoints default to API "
                            "only; this value is pushed to the proxbox-api "
                            "backend."
                        ),
                        max_length=16,
                        verbose_name="Access methods",
                    ),
                ),
            ],
        ),
    ]
