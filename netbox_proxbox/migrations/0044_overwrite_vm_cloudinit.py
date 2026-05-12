"""Add ProxboxPluginSettings.overwrite_vm_cloudinit gate flag for issue #363."""

from django.db import migrations, models


SETTINGS_TABLE = "netbox_proxbox_proxboxpluginsettings"


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0043_proxmoxvmcloudinit"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql=(
                        f'ALTER TABLE "{SETTINGS_TABLE}" '
                        f'ADD COLUMN IF NOT EXISTS "overwrite_vm_cloudinit" '
                        f'boolean NOT NULL DEFAULT TRUE;'
                    ),
                    reverse_sql=(
                        f'ALTER TABLE "{SETTINGS_TABLE}" '
                        f'DROP COLUMN IF EXISTS "overwrite_vm_cloudinit";'
                    ),
                ),
            ],
            state_operations=[
                migrations.AddField(
                    model_name="proxboxpluginsettings",
                    name="overwrite_vm_cloudinit",
                    field=models.BooleanField(
                        default=True,
                        verbose_name="Overwrite VM cloud-init",
                        help_text=(
                            "When disabled, sync never updates the "
                            "ProxmoxVMCloudInit row (ciuser, sshkeys, "
                            "ipconfig0) on existing NetBox virtual machines."
                        ),
                    ),
                ),
            ],
        ),
    ]
