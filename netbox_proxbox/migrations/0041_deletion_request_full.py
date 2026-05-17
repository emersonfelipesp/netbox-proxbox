"""Sub-PR H (#385): promote DeletionRequest to the full safe-delete schema.

Idempotent: every ``AddField`` is wrapped through ``add_field_idempotent``
so reporter-style installs whose legacy lineage already added these columns
do not abort with ``DuplicateColumn``.
"""

from __future__ import annotations

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

from netbox_proxbox.migrations._idempotent_ops import add_field_idempotent


class Migration(migrations.Migration):

    dependencies = [
        ("netbox_proxbox", "0040_apply_job_full"),
    ]

    operations = [
        add_field_idempotent(
            model_name="deletionrequest",
            field_name="branch_id",
            field=models.IntegerField(blank=True, null=True),
        ),
        add_field_idempotent(
            model_name="deletionrequest",
            field_name="branch_name",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        add_field_idempotent(
            model_name="deletionrequest",
            field_name="requested_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="proxbox_deletion_requests_requested",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        add_field_idempotent(
            model_name="deletionrequest",
            field_name="authorizer",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="proxbox_deletion_requests_authorized",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        add_field_idempotent(
            model_name="deletionrequest",
            field_name="state",
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
        add_field_idempotent(
            model_name="deletionrequest",
            field_name="vmid",
            field=models.IntegerField(blank=True, null=True),
        ),
        add_field_idempotent(
            model_name="deletionrequest",
            field_name="node",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        add_field_idempotent(
            model_name="deletionrequest",
            field_name="kind",
            field=models.CharField(
                choices=[("qemu", "qemu"), ("lxc", "lxc")],
                default="qemu",
                max_length=8,
            ),
        ),
        add_field_idempotent(
            model_name="deletionrequest",
            field_name="metadata_snapshot",
            field=models.JSONField(blank=True, default=dict),
        ),
        add_field_idempotent(
            model_name="deletionrequest",
            field_name="reject_reason",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        add_field_idempotent(
            model_name="deletionrequest",
            field_name="executor_run_uuid",
            field=models.UUIDField(blank=True, null=True),
        ),
        add_field_idempotent(
            model_name="deletionrequest",
            field_name="requested_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        add_field_idempotent(
            model_name="deletionrequest",
            field_name="approved_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        add_field_idempotent(
            model_name="deletionrequest",
            field_name="executed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
