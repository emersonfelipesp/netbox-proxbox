from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0032_proxmoxendpoint_timeout_retries_pluginsettings_proxmox_defaults"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql='ALTER TABLE "netbox_proxbox_proxboxpluginsettings" ADD COLUMN IF NOT EXISTS "overwrite_device_role" boolean NOT NULL DEFAULT true;',
                    reverse_sql='ALTER TABLE "netbox_proxbox_proxboxpluginsettings" DROP COLUMN IF EXISTS "overwrite_device_role";',
                ),
                migrations.RunSQL(
                    sql='ALTER TABLE "netbox_proxbox_proxboxpluginsettings" ADD COLUMN IF NOT EXISTS "overwrite_device_type" boolean NOT NULL DEFAULT true;',
                    reverse_sql='ALTER TABLE "netbox_proxbox_proxboxpluginsettings" DROP COLUMN IF EXISTS "overwrite_device_type";',
                ),
                migrations.RunSQL(
                    sql='ALTER TABLE "netbox_proxbox_proxboxpluginsettings" ADD COLUMN IF NOT EXISTS "overwrite_device_tags" boolean NOT NULL DEFAULT true;',
                    reverse_sql='ALTER TABLE "netbox_proxbox_proxboxpluginsettings" DROP COLUMN IF EXISTS "overwrite_device_tags";',
                ),
                migrations.RunSQL(
                    sql='ALTER TABLE "netbox_proxbox_proxboxpluginsettings" ADD COLUMN IF NOT EXISTS "overwrite_vm_role" boolean NOT NULL DEFAULT true;',
                    reverse_sql='ALTER TABLE "netbox_proxbox_proxboxpluginsettings" DROP COLUMN IF EXISTS "overwrite_vm_role";',
                ),
                migrations.RunSQL(
                    sql='ALTER TABLE "netbox_proxbox_proxboxpluginsettings" ADD COLUMN IF NOT EXISTS "overwrite_vm_tags" boolean NOT NULL DEFAULT true;',
                    reverse_sql='ALTER TABLE "netbox_proxbox_proxboxpluginsettings" DROP COLUMN IF EXISTS "overwrite_vm_tags";',
                ),
            ],
            state_operations=[
                migrations.AddField(
                    model_name="proxboxpluginsettings",
                    name="overwrite_device_role",
                    field=models.BooleanField(
                        default=True,
                        verbose_name="Overwrite device role",
                        help_text=(
                            "When disabled, sync never changes the device role on existing Proxmox node devices "
                            "that already have a role assigned. The role is still set when the device is first created."
                        ),
                    ),
                ),
                migrations.AddField(
                    model_name="proxboxpluginsettings",
                    name="overwrite_device_type",
                    field=models.BooleanField(
                        default=True,
                        verbose_name="Overwrite device type",
                        help_text=(
                            "When disabled, sync never changes the device type on existing Proxmox node devices "
                            "that already have a device type assigned. The device type is still set at create time."
                        ),
                    ),
                ),
                migrations.AddField(
                    model_name="proxboxpluginsettings",
                    name="overwrite_device_tags",
                    field=models.BooleanField(
                        default=True,
                        verbose_name="Overwrite device tags",
                        help_text=(
                            "When disabled, sync never changes the tags on existing Proxmox node devices "
                            "that already have tags assigned. Tags are still applied when the device is first created."
                        ),
                    ),
                ),
                migrations.AddField(
                    model_name="proxboxpluginsettings",
                    name="overwrite_vm_role",
                    field=models.BooleanField(
                        default=True,
                        verbose_name="Overwrite VM role",
                        help_text=(
                            "When disabled, sync never changes the role on existing NetBox virtual machines "
                            "that already have a role assigned. The role is still set when the VM is first created."
                        ),
                    ),
                ),
                migrations.AddField(
                    model_name="proxboxpluginsettings",
                    name="overwrite_vm_tags",
                    field=models.BooleanField(
                        default=True,
                        verbose_name="Overwrite VM tags",
                        help_text=(
                            "When disabled, sync never changes the tags on existing NetBox virtual machines "
                            "that already have tags assigned. Tags are still applied when the VM is first created."
                        ),
                    ),
                ),
            ],
        ),
    ]
