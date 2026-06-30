from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0053_tenant_from_cluster"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql=(
                        'ALTER TABLE "netbox_proxbox_proxmoxendpoint" '
                        'ADD COLUMN IF NOT EXISTS "ssh_credential_source" '
                        "varchar(32) NOT NULL DEFAULT 'dedicated';"
                    ),
                    reverse_sql=(
                        'ALTER TABLE "netbox_proxbox_proxmoxendpoint" '
                        'DROP COLUMN IF EXISTS "ssh_credential_source";'
                    ),
                )
            ],
            state_operations=[
                migrations.AddField(
                    model_name="proxmoxendpoint",
                    name="ssh_credential_source",
                    field=models.CharField(
                        choices=[
                            ("dedicated", "Dedicated SSH credential"),
                            (
                                "reuse_endpoint",
                                "Reuse endpoint username/password",
                            ),
                        ],
                        default="dedicated",
                        help_text=(
                            "Choose a dedicated SSH credential or reuse this "
                            "endpoint's Proxmox username/password for SSH. "
                            "Reuse strips the realm (for example, root@pam "
                            "becomes root); only PAM-backed Proxmox users "
                            "usually map to local SSH accounts."
                        ),
                        max_length=32,
                        verbose_name="SSH credential source",
                    ),
                ),
            ],
        ),
    ]
