"""Initial schema for standalone PBS inventory models."""

from __future__ import annotations

import django.db.models.deletion
import taggit.managers
import utilities.json
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("extras", "0002_squashed_0059"),
    ]

    operations = [
        migrations.CreateModel(
            name="PBSPluginSettings",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False
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
                        default="default", editable=False, max_length=32, unique=True
                    ),
                ),
                ("proxbox_api_url", models.CharField(blank=True, max_length=255)),
                ("proxbox_api_key", models.CharField(blank=True, max_length=255)),
                ("branching_enabled", models.BooleanField(default=False)),
                (
                    "branch_name_prefix",
                    models.CharField(default="pbs-sync", max_length=64),
                ),
                (
                    "branch_on_conflict",
                    models.CharField(
                        choices=[
                            ("abort", "Abort and leave branch open for review"),
                            ("overwrite", "Overwrite by merging despite conflicts"),
                        ],
                        default="abort",
                        max_length=16,
                    ),
                ),
                (
                    "tags",
                    taggit.managers.TaggableManager(
                        through="extras.TaggedItem", to="extras.Tag"
                    ),
                ),
            ],
            options={
                "verbose_name": "PBS plugin settings",
                "verbose_name_plural": "PBS plugin settings",
            },
        ),
        migrations.CreateModel(
            name="PBSServer",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False
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
                ("name", models.CharField(max_length=255, unique=True)),
                ("host", models.CharField(max_length=255)),
                ("port", models.IntegerField(default=8007)),
                ("token_id", models.CharField(max_length=255)),
                ("fingerprint", models.CharField(blank=True, max_length=255)),
                ("verify_ssl", models.BooleanField(default=True)),
                ("status", models.CharField(blank=True, max_length=32)),
                ("version", models.CharField(blank=True, max_length=128)),
                ("last_seen_at", models.DateTimeField(blank=True, null=True)),
                (
                    "tags",
                    taggit.managers.TaggableManager(
                        through="extras.TaggedItem", to="extras.Tag"
                    ),
                ),
            ],
            options={
                "verbose_name": "PBS server",
                "verbose_name_plural": "PBS servers",
                "ordering": ("name",),
            },
        ),
        migrations.CreateModel(
            name="PBSDatastore",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False
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
                ("name", models.CharField(max_length=255)),
                ("path", models.CharField(max_length=1024)),
                ("used_bytes", models.BigIntegerField(blank=True, null=True)),
                ("total_bytes", models.BigIntegerField(blank=True, null=True)),
                ("avail_bytes", models.BigIntegerField(blank=True, null=True)),
                ("gc_status", models.CharField(blank=True, max_length=32)),
                ("comment", models.CharField(blank=True, max_length=1024)),
                ("last_seen_at", models.DateTimeField(blank=True, null=True)),
                (
                    "server",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="datastores",
                        to="netbox_pbs.pbsserver",
                    ),
                ),
                (
                    "tags",
                    taggit.managers.TaggableManager(
                        through="extras.TaggedItem", to="extras.Tag"
                    ),
                ),
            ],
            options={
                "verbose_name": "PBS datastore",
                "verbose_name_plural": "PBS datastores",
                "ordering": ("server", "name"),
            },
        ),
        migrations.AddConstraint(
            model_name="pbsdatastore",
            constraint=models.UniqueConstraint(
                fields=("server", "name"),
                name="netbox_pbs_datastore_identity",
            ),
        ),
        migrations.CreateModel(
            name="PBSSnapshot",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False
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
                ("datastore_name", models.CharField(max_length=255)),
                ("backup_type", models.CharField(max_length=16)),
                ("backup_id", models.CharField(max_length=255)),
                ("backup_time", models.DateTimeField(blank=True, null=True)),
                ("size_bytes", models.BigIntegerField(blank=True, null=True)),
                ("owner", models.CharField(blank=True, max_length=255)),
                ("protected", models.BooleanField(default=False)),
                ("comment", models.CharField(blank=True, max_length=1024)),
                ("verification_state", models.CharField(blank=True, max_length=32)),
                ("last_seen_at", models.DateTimeField(blank=True, null=True)),
                (
                    "server",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="snapshots",
                        to="netbox_pbs.pbsserver",
                    ),
                ),
                (
                    "tags",
                    taggit.managers.TaggableManager(
                        through="extras.TaggedItem", to="extras.Tag"
                    ),
                ),
            ],
            options={
                "verbose_name": "PBS snapshot",
                "verbose_name_plural": "PBS snapshots",
                "ordering": (
                    "server",
                    "datastore_name",
                    "backup_type",
                    "backup_id",
                    "-backup_time",
                ),
            },
        ),
        migrations.AddConstraint(
            model_name="pbssnapshot",
            constraint=models.UniqueConstraint(
                fields=(
                    "server",
                    "datastore_name",
                    "backup_type",
                    "backup_id",
                    "backup_time",
                ),
                name="netbox_pbs_snapshot_identity",
            ),
        ),
        migrations.CreateModel(
            name="PBSJob",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False
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
                ("job_type", models.CharField(max_length=16)),
                ("job_id", models.CharField(max_length=255)),
                ("store", models.CharField(blank=True, max_length=255)),
                ("schedule", models.CharField(blank=True, max_length=255)),
                ("comment", models.CharField(blank=True, max_length=1024)),
                ("disable", models.BooleanField(default=False)),
                ("last_run_state", models.CharField(blank=True, max_length=32)),
                ("last_run_endtime", models.DateTimeField(blank=True, null=True)),
                ("next_run", models.DateTimeField(blank=True, null=True)),
                ("last_seen_at", models.DateTimeField(blank=True, null=True)),
                (
                    "server",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="jobs",
                        to="netbox_pbs.pbsserver",
                    ),
                ),
                (
                    "tags",
                    taggit.managers.TaggableManager(
                        through="extras.TaggedItem", to="extras.Tag"
                    ),
                ),
            ],
            options={
                "verbose_name": "PBS job",
                "verbose_name_plural": "PBS jobs",
                "ordering": ("server", "job_type", "job_id"),
            },
        ),
        migrations.AddConstraint(
            model_name="pbsjob",
            constraint=models.UniqueConstraint(
                fields=("server", "job_type", "job_id"),
                name="netbox_pbs_job_identity",
            ),
        ),
    ]
