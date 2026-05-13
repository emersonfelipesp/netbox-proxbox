"""Create the six read-only PBS domain models.

PR C2 of issue #325. Each model mirrors a PBS object surface: endpoint,
node, datastore, backup group, snapshot, and scheduled-job status. The
endpoint is the only writable model on the NetBox side; the other five
are reflected from PBS by the read-only sync that lands in PR C3.
"""

import django.core.validators
import django.db.models.deletion
import taggit.managers
import utilities.json
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("extras", "0001_initial"),
        ("netbox_pbs", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="PBSEndpoint",
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
                (
                    "port",
                    models.PositiveIntegerField(
                        default=8007,
                        validators=[
                            django.core.validators.MinValueValidator(1),
                            django.core.validators.MaxValueValidator(65535),
                        ],
                    ),
                ),
                ("token_id", models.CharField(max_length=255)),
                ("token_value", models.CharField(max_length=255)),
                ("fingerprint", models.CharField(blank=True, max_length=128)),
                ("verify_ssl", models.BooleanField(default=True)),
                ("timeout", models.PositiveIntegerField(default=30)),
                ("last_seen_at", models.DateTimeField(blank=True, null=True)),
                (
                    "tags",
                    taggit.managers.TaggableManager(
                        through="extras.TaggedItem", to="extras.Tag"
                    ),
                ),
            ],
            options={
                "verbose_name": "PBS endpoint",
                "verbose_name_plural": "PBS endpoints",
                "ordering": ("name", "pk"),
            },
        ),
        migrations.CreateModel(
            name="PBSNode",
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
                ("hostname", models.CharField(max_length=255)),
                ("version", models.CharField(blank=True, max_length=64)),
                ("uptime_seconds", models.BigIntegerField(blank=True, null=True)),
                ("cpu_pct", models.FloatField(blank=True, null=True)),
                ("memory_used", models.BigIntegerField(blank=True, null=True)),
                ("memory_total", models.BigIntegerField(blank=True, null=True)),
                ("last_seen_at", models.DateTimeField(blank=True, null=True)),
                (
                    "endpoint",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="nodes",
                        to="netbox_pbs.pbsendpoint",
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
                "verbose_name": "PBS node",
                "verbose_name_plural": "PBS nodes",
                "ordering": ("endpoint", "hostname"),
                "constraints": [
                    models.UniqueConstraint(
                        fields=("endpoint", "hostname"),
                        name="netbox_pbs_pbsnode_identity",
                    ),
                ],
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
                ("path", models.CharField(blank=True, max_length=512)),
                ("total_bytes", models.BigIntegerField(blank=True, null=True)),
                ("used_bytes", models.BigIntegerField(blank=True, null=True)),
                ("available_bytes", models.BigIntegerField(blank=True, null=True)),
                (
                    "gc_status",
                    models.CharField(default="unknown", max_length=16),
                ),
                ("last_gc_at", models.DateTimeField(blank=True, null=True)),
                (
                    "endpoint",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="datastores",
                        to="netbox_pbs.pbsendpoint",
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
                "ordering": ("endpoint", "name"),
                "constraints": [
                    models.UniqueConstraint(
                        fields=("endpoint", "name"),
                        name="netbox_pbs_pbsdatastore_identity",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="PBSBackupGroup",
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
                ("backup_type", models.CharField(max_length=8)),
                ("backup_id", models.CharField(max_length=64)),
                ("owner", models.CharField(blank=True, max_length=128)),
                ("comment", models.CharField(blank=True, max_length=512)),
                (
                    "datastore",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="backup_groups",
                        to="netbox_pbs.pbsdatastore",
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
                "verbose_name": "PBS backup group",
                "verbose_name_plural": "PBS backup groups",
                "ordering": ("datastore", "backup_type", "backup_id"),
                "constraints": [
                    models.UniqueConstraint(
                        fields=("datastore", "backup_type", "backup_id"),
                        name="netbox_pbs_pbsbackupgroup_identity",
                    ),
                ],
            },
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
                ("backup_time", models.DateTimeField()),
                ("size_bytes", models.BigIntegerField(blank=True, null=True)),
                ("encrypted", models.BooleanField(default=False)),
                ("verified", models.CharField(default="none", max_length=16)),
                ("protected", models.BooleanField(default=False)),
                ("comment", models.CharField(blank=True, max_length=512)),
                (
                    "files",
                    models.JSONField(
                        blank=True,
                        default=list,
                        encoder=utilities.json.CustomFieldJSONEncoder,
                    ),
                ),
                (
                    "backup_group",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="snapshots",
                        to="netbox_pbs.pbsbackupgroup",
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
                "ordering": ("backup_group", "-backup_time"),
                "constraints": [
                    models.UniqueConstraint(
                        fields=("backup_group", "backup_time"),
                        name="netbox_pbs_pbssnapshot_identity",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="PBSJobStatus",
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
                ("job_id", models.CharField(max_length=128)),
                ("enabled", models.BooleanField(default=True)),
                ("last_run_at", models.DateTimeField(blank=True, null=True)),
                (
                    "last_run_state",
                    models.CharField(default="unknown", max_length=16),
                ),
                (
                    "last_run_duration_seconds",
                    models.PositiveIntegerField(blank=True, null=True),
                ),
                ("next_run_at", models.DateTimeField(blank=True, null=True)),
                (
                    "endpoint",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="jobs",
                        to="netbox_pbs.pbsendpoint",
                    ),
                ),
                (
                    "datastore",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="jobs",
                        to="netbox_pbs.pbsdatastore",
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
                "verbose_name": "PBS job status",
                "verbose_name_plural": "PBS job statuses",
                "ordering": ("endpoint", "job_type", "job_id"),
                "constraints": [
                    models.UniqueConstraint(
                        fields=("endpoint", "job_type", "job_id"),
                        name="netbox_pbs_pbsjobstatus_identity",
                    ),
                ],
            },
        ),
    ]
