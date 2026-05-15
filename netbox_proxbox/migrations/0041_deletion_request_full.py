"""Sub-PR H (#385): promote DeletionRequest to the full safe-delete schema."""

from __future__ import annotations

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("netbox_proxbox", "0040_apply_job_full"),
    ]

    operations = [
        migrations.AddField(
            model_name="deletionrequest",
            name="branch",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="netbox_branching.branch",
            ),
        ),
        migrations.AddField(
            model_name="deletionrequest",
            name="requested_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="proxbox_deletion_requests_requested",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="deletionrequest",
            name="authorizer",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="proxbox_deletion_requests_authorized",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="deletionrequest",
            name="state",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("approved", "Approved"),
                    ("rejected", "Rejected"),
                    ("executing", "Executing"),
                    ("succeeded", "Succeeded"),
                    ("failed", "Failed"),
                ],
                default="pending",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="deletionrequest",
            name="vmid",
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="deletionrequest",
            name="node",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="deletionrequest",
            name="kind",
            field=models.CharField(
                choices=[("qemu", "qemu"), ("lxc", "lxc")],
                default="qemu",
                max_length=8,
            ),
        ),
        migrations.AddField(
            model_name="deletionrequest",
            name="metadata_snapshot",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="deletionrequest",
            name="reject_reason",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="deletionrequest",
            name="executor_run_uuid",
            field=models.UUIDField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="deletionrequest",
            name="requested_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="deletionrequest",
            name="approved_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="deletionrequest",
            name="executed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
