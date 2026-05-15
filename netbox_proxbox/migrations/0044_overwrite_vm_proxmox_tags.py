from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0043_pluginsettings_warn_plaintext"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql=(
                        'ALTER TABLE "netbox_proxbox_proxboxpluginsettings" '
                        'ADD COLUMN IF NOT EXISTS "overwrite_vm_proxmox_tags" boolean NOT NULL DEFAULT TRUE;'
                    ),
                    reverse_sql=(
                        'ALTER TABLE "netbox_proxbox_proxboxpluginsettings" '
                        'DROP COLUMN IF EXISTS "overwrite_vm_proxmox_tags";'
                    ),
                ),
            ],
            state_operations=[
                migrations.AddField(
                    model_name="proxboxpluginsettings",
                    name="overwrite_vm_proxmox_tags",
                    field=models.BooleanField(
                        default=True,
                        verbose_name="Sync Proxmox tags",
                        help_text=(
                            "When enabled, Proxmox VM tags (the `;`-separated `tags` field on QEMU/LXC "
                            "config) are mirrored as NetBox tags on the synced VirtualMachine. Tag colors "
                            "match the Proxmox `tag-style` color-map when available, otherwise a stable "
                            "deterministic color is used. When disabled, Proxmox-sourced tags are never "
                            "created or attached."
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
                        'ADD COLUMN IF NOT EXISTS "overwrite_vm_proxmox_tags" boolean NULL;'
                    ),
                    reverse_sql=(
                        'ALTER TABLE "netbox_proxbox_proxmoxendpoint" '
                        'DROP COLUMN IF EXISTS "overwrite_vm_proxmox_tags";'
                    ),
                ),
            ],
            state_operations=[
                migrations.AddField(
                    model_name="proxmoxendpoint",
                    name="overwrite_vm_proxmox_tags",
                    field=models.BooleanField(
                        blank=True,
                        null=True,
                        verbose_name="Sync Proxmox tags",
                        help_text="Per-endpoint override for the global Proxbox setting. Leave blank to inherit.",
                    ),
                ),
            ],
        ),
    ]
