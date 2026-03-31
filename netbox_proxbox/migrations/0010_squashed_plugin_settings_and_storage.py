"""Squash plugin settings/storage additions introduced after 0009."""

import taggit.managers
import utilities.json
from django.db import migrations, models


class Migration(migrations.Migration):
    replaces = [
        ("netbox_proxbox", "0010_proxbox_plugin_settings"),
        ("netbox_proxbox", "0011_proxmoxstorage"),
        ("netbox_proxbox", "0012_proxboxpluginsettings_proxbox_fetch_max_concurrency"),
    ]

    dependencies = [
        ("extras", "0134_owner"),
        ("netbox_proxbox", "0009_squashed_post_v006b2_to_v008"),
        ("users", "0015_owner"),
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
    ]
