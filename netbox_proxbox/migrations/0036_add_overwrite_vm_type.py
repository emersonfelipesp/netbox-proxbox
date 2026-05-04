from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0035_overwrite_fields_expansion"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql=(
                        'ALTER TABLE "netbox_proxbox_proxboxpluginsettings" '
                        'ADD COLUMN IF NOT EXISTS "overwrite_vm_type" boolean NOT NULL DEFAULT TRUE;'
                    ),
                    reverse_sql=(
                        'ALTER TABLE "netbox_proxbox_proxboxpluginsettings" '
                        'DROP COLUMN IF EXISTS "overwrite_vm_type";'
                    ),
                ),
            ],
            state_operations=[
                migrations.AddField(
                    model_name="proxboxpluginsettings",
                    name="overwrite_vm_type",
                    field=models.BooleanField(
                        default=True,
                        verbose_name="Overwrite VM type",
                        help_text=(
                            "When disabled, sync never changes the type on existing NetBox virtual machines "
                            "that already have a type assigned. The type is still set when the VM is first created."
                        ),
                    ),
                ),
            ],
        ),
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql=(
                        'ALTER TABLE "netbox_proxbox_proxmoxendpoint" '
                        'ADD COLUMN IF NOT EXISTS "overwrite_vm_type" boolean NULL;'
                    ),
                    reverse_sql=(
                        'ALTER TABLE "netbox_proxbox_proxmoxendpoint" '
                        'DROP COLUMN IF EXISTS "overwrite_vm_type";'
                    ),
                ),
            ],
            state_operations=[
                migrations.AddField(
                    model_name="proxmoxendpoint",
                    name="overwrite_vm_type",
                    field=models.BooleanField(
                        blank=True,
                        null=True,
                        verbose_name="Overwrite VM type",
                        help_text="Per-endpoint override for the global Proxbox setting. Leave blank to inherit.",
                    ),
                ),
            ],
        ),
    ]
