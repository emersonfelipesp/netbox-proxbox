"""Squash plugin settings/storage additions introduced after 0009."""

import django.db.models.deletion
import taggit.managers
import utilities.json
from django.db import migrations, models


class Migration(migrations.Migration):
    replaces = [
        ("netbox_proxbox", "0010_proxbox_plugin_settings"),
        ("netbox_proxbox", "0011_proxmoxstorage"),
        ("netbox_proxbox", "0011_alter_vmbackup_storage"),
        ("netbox_proxbox", "0012_proxboxpluginsettings_proxbox_fetch_max_concurrency"),
        ("netbox_proxbox", "0011_storage_relations"),
        ("netbox_proxbox", "0011_storage_relationship_foreignkeys"),
        ("netbox_proxbox", "0012_vmtaskhistory"),
    ]

    dependencies = [
        ("extras", "0134_owner"),
        ("netbox_proxbox", "0009_squashed_post_v006b2_to_v008"),
        ("users", "0015_owner"),
        ("virtualization", "0052_gfk_indexes"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProxboxPluginSettings",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("last_updated", models.DateTimeField(auto_now=True, null=True)),
                (
                    "custom_field_data",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        encoder=utilities.json.CustomFieldJSONEncoder,
                    ),
                ),
                (
                    "singleton_key",
                    models.CharField(
                        default="default",
                        editable=False,
                        max_length=32,
                        unique=True,
                    ),
                ),
                (
                    "use_guest_agent_interface_name",
                    models.BooleanField(
                        default=True,
                        help_text=(
                            "When enabled, VM interface names use QEMU guest-agent names when "
                            "available (for example ens18) instead of generic Proxmox labels "
                            "(for example net0/nic0)."
                        ),
                        verbose_name="Use guest agent interface name",
                    ),
                ),
                (
                    "proxbox_fetch_max_concurrency",
                    models.PositiveSmallIntegerField(
                        default=8,
                        help_text=(
                            "Maximum number of parallel Proxmox fetch operations per sync "
                            "stage. Higher values can speed up multi-cluster discovery but "
                            "may increase load."
                        ),
                        verbose_name="Proxmox fetch max concurrency",
                    ),
                ),
                (
                    "tags",
                    taggit.managers.TaggableManager(
                        through="extras.TaggedItem",
                        to="extras.Tag",
                    ),
                ),
            ],
            options={
                "verbose_name": "Proxbox plugin settings",
                "verbose_name_plural": "Proxbox plugin settings",
            },
        ),
        migrations.CreateModel(
            name="ProxmoxStorage",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("last_updated", models.DateTimeField(auto_now=True, null=True)),
                (
                    "custom_field_data",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        encoder=utilities.json.CustomFieldJSONEncoder,
                    ),
                ),
                ("cluster", models.CharField(max_length=255)),
                ("name", models.CharField(max_length=255)),
                ("storage_type", models.CharField(blank=True, max_length=100, null=True)),
                ("content", models.CharField(blank=True, max_length=255, null=True)),
                ("path", models.CharField(blank=True, max_length=255, null=True)),
                ("nodes", models.CharField(blank=True, max_length=255, null=True)),
                ("shared", models.BooleanField(default=False)),
                ("enabled", models.BooleanField(default=True)),
                (
                    "tags",
                    taggit.managers.TaggableManager(
                        through="extras.TaggedItem",
                        to="extras.Tag",
                    ),
                ),
            ],
            options={
                "verbose_name": "Proxmox Storage",
                "verbose_name_plural": "Proxmox Storages",
                "ordering": ("cluster", "name"),
                "unique_together": {("cluster", "name")},
            },
        ),
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
        migrations.AlterField(
            model_name="vmbackup",
            name="storage",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.CreateModel(
            name="VMTaskHistory",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("last_updated", models.DateTimeField(auto_now=True, null=True)),
                (
                    "custom_field_data",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        encoder=utilities.json.CustomFieldJSONEncoder,
                    ),
                ),
                ("vm_type", models.CharField(default="unknown", max_length=16)),
                ("upid", models.CharField(max_length=255, unique=True)),
                ("node", models.CharField(max_length=255)),
                ("pid", models.IntegerField(blank=True, null=True)),
                ("pstart", models.IntegerField(blank=True, null=True)),
                ("task_id", models.CharField(blank=True, max_length=255, null=True)),
                ("task_type", models.CharField(max_length=255)),
                ("username", models.CharField(max_length=255)),
                ("start_time", models.DateTimeField()),
                ("end_time", models.DateTimeField(blank=True, null=True)),
                ("description", models.TextField()),
                ("status", models.CharField(max_length=255)),
                ("task_state", models.CharField(blank=True, max_length=255, null=True)),
                ("exitstatus", models.CharField(blank=True, max_length=255, null=True)),
                (
                    "tags",
                    taggit.managers.TaggableManager(
                        through="extras.TaggedItem",
                        to="extras.Tag",
                    ),
                ),
                (
                    "virtual_machine",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="task_histories",
                        to="virtualization.virtualmachine",
                    ),
                ),
            ],
            options={
                "verbose_name": "VM Task History",
                "verbose_name_plural": "VM Task Histories",
                "ordering": ("-start_time", "virtual_machine", "node"),
            },
        ),
    ]
