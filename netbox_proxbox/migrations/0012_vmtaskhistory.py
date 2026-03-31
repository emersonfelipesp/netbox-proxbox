"""Add VM task history records linked to NetBox virtual machines."""

import django.db.models.deletion
import taggit.managers
import utilities.json
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("extras", "0134_owner"),
        ("netbox_proxbox", "0011_storage_relations"),
        ("users", "0015_owner"),
        ("virtualization", "0052_gfk_indexes"),
    ]

    operations = [
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
