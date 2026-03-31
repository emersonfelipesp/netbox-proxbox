"""Add explicit storage relations for backups, snapshots, and virtual disks."""

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0010_squashed_plugin_settings_and_storage"),
        ("virtualization", "0052_gfk_indexes"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProxmoxStorageVirtualDisk",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "proxmox_storage",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="virtual_disk_links",
                        to="netbox_proxbox.proxmoxstorage",
                    ),
                ),
                (
                    "virtual_disk",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="proxmox_storage_links",
                        to="virtualization.virtualdisk",
                    ),
                ),
            ],
            options={
                "unique_together": {("proxmox_storage", "virtual_disk")},
            },
        ),
        migrations.AddField(
            model_name="proxmoxstorage",
            name="virtual_disks",
            field=models.ManyToManyField(
                blank=True,
                related_name="proxmox_storages",
                through="netbox_proxbox.ProxmoxStorageVirtualDisk",
                to="virtualization.virtualdisk",
            ),
        ),
        migrations.AddField(
            model_name="vmbackup",
            name="proxmox_storage",
            field=models.ForeignKey(
                blank=True,
                help_text="Related Proxmox storage object.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="vm_backups",
                to="netbox_proxbox.proxmoxstorage",
            ),
        ),
        migrations.AddField(
            model_name="vmsnapshot",
            name="proxmox_storage",
            field=models.ForeignKey(
                blank=True,
                help_text="Related Proxmox storage object.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="vm_snapshots",
                to="netbox_proxbox.proxmoxstorage",
            ),
        ),
    ]
