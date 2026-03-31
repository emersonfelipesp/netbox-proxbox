"""Add Proxmox storage inventory model."""

import taggit.managers
import utilities.json
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("extras", "0134_owner"),
        ("netbox_proxbox", "0010_proxbox_plugin_settings"),
        ("users", "0015_owner"),
    ]

    operations = [
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
