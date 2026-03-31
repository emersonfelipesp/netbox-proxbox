"""Link VM backups and snapshots to Proxmox storage rows."""

from __future__ import annotations

from django.db import migrations, models


def _populate_backup_storage_relation(apps, schema_editor):
    vm_backup = apps.get_model("netbox_proxbox", "VMBackup")
    proxmox_storage = apps.get_model("netbox_proxbox", "ProxmoxStorage")

    for backup in vm_backup.objects.select_related("virtual_machine__cluster").all():
        storage_value = str(getattr(backup, "storage", "") or "").strip()
        if not storage_value:
            continue

        storage = None
        if storage_value.isdigit():
            storage = proxmox_storage.objects.filter(pk=int(storage_value)).first()
        if storage is None:
            storage_qs = proxmox_storage.objects.filter(name=storage_value)
            cluster = getattr(
                getattr(backup.virtual_machine, "cluster", None), "name", None
            )
            if cluster:
                storage_qs = storage_qs.filter(cluster=cluster)
            storage = storage_qs.order_by("id").first()

        if storage is None:
            backup.storage = None
            backup.save(update_fields=["storage"])
            continue

        backup.storage = str(storage.pk)
        backup.save(update_fields=["storage"])


class Migration(migrations.Migration):

    dependencies = [
        ("netbox_proxbox", "0010_squashed_plugin_settings_and_storage"),
    ]

    operations = [
        migrations.AddField(
            model_name="vmsnapshot",
            name="storage",
            field=models.ForeignKey(
                blank=True,
                help_text="Storage associated with the snapshot.",
                null=True,
                on_delete=models.SET_NULL,
                related_name="storage_snapshots",
                to="netbox_proxbox.proxmoxstorage",
            ),
        ),
        migrations.RunPython(
            _populate_backup_storage_relation,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="vmbackup",
            name="storage",
            field=models.ForeignKey(
                blank=True,
                help_text="Storage of the backup.",
                null=True,
                on_delete=models.SET_NULL,
                related_name="storage_backups",
                to="netbox_proxbox.proxmoxstorage",
            ),
        ),
    ]
