from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0033_pluginsettings_controlled_fields"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql='ALTER TABLE "netbox_proxbox_proxmoxendpoint" ADD COLUMN IF NOT EXISTS "overwrite_device_role" boolean NULL;',
                    reverse_sql='ALTER TABLE "netbox_proxbox_proxmoxendpoint" DROP COLUMN IF EXISTS "overwrite_device_role";',
                ),
                migrations.RunSQL(
                    sql='ALTER TABLE "netbox_proxbox_proxmoxendpoint" ADD COLUMN IF NOT EXISTS "overwrite_device_type" boolean NULL;',
                    reverse_sql='ALTER TABLE "netbox_proxbox_proxmoxendpoint" DROP COLUMN IF EXISTS "overwrite_device_type";',
                ),
                migrations.RunSQL(
                    sql='ALTER TABLE "netbox_proxbox_proxmoxendpoint" ADD COLUMN IF NOT EXISTS "overwrite_device_tags" boolean NULL;',
                    reverse_sql='ALTER TABLE "netbox_proxbox_proxmoxendpoint" DROP COLUMN IF EXISTS "overwrite_device_tags";',
                ),
                migrations.RunSQL(
                    sql='ALTER TABLE "netbox_proxbox_proxmoxendpoint" ADD COLUMN IF NOT EXISTS "overwrite_vm_role" boolean NULL;',
                    reverse_sql='ALTER TABLE "netbox_proxbox_proxmoxendpoint" DROP COLUMN IF EXISTS "overwrite_vm_role";',
                ),
                migrations.RunSQL(
                    sql='ALTER TABLE "netbox_proxbox_proxmoxendpoint" ADD COLUMN IF NOT EXISTS "overwrite_vm_tags" boolean NULL;',
                    reverse_sql='ALTER TABLE "netbox_proxbox_proxmoxendpoint" DROP COLUMN IF EXISTS "overwrite_vm_tags";',
                ),
            ],
            state_operations=[
                migrations.AddField(
                    model_name="proxmoxendpoint",
                    name="overwrite_device_role",
                    field=models.BooleanField(
                        blank=True,
                        null=True,
                        verbose_name="Overwrite device role",
                        help_text="Per-endpoint override for the global Proxbox setting. Leave blank to inherit.",
                    ),
                ),
                migrations.AddField(
                    model_name="proxmoxendpoint",
                    name="overwrite_device_type",
                    field=models.BooleanField(
                        blank=True,
                        null=True,
                        verbose_name="Overwrite device type",
                        help_text="Per-endpoint override for the global Proxbox setting. Leave blank to inherit.",
                    ),
                ),
                migrations.AddField(
                    model_name="proxmoxendpoint",
                    name="overwrite_device_tags",
                    field=models.BooleanField(
                        blank=True,
                        null=True,
                        verbose_name="Overwrite device tags",
                        help_text="Per-endpoint override for the global Proxbox setting. Leave blank to inherit.",
                    ),
                ),
                migrations.AddField(
                    model_name="proxmoxendpoint",
                    name="overwrite_vm_role",
                    field=models.BooleanField(
                        blank=True,
                        null=True,
                        verbose_name="Overwrite VM role",
                        help_text="Per-endpoint override for the global Proxbox setting. Leave blank to inherit.",
                    ),
                ),
                migrations.AddField(
                    model_name="proxmoxendpoint",
                    name="overwrite_vm_tags",
                    field=models.BooleanField(
                        blank=True,
                        null=True,
                        verbose_name="Merge VM tags",
                        help_text="Per-endpoint override for the global Proxbox setting. Leave blank to inherit.",
                    ),
                ),
            ],
        ),
    ]
