"""Sub-PR E (#382): promote ProxmoxApplyJob to the full intent apply schema."""

from __future__ import annotations

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("netbox_proxbox", "0039_intent_custom_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="proxmoxapplyjob",
            name="branch_id",
            field=models.IntegerField(
                blank=True,
                help_text=(
                    "Primary key of the merged netbox-branching Branch that "
                    "triggered this run."
                ),
                null=True,
                verbose_name="Branch ID",
            ),
        ),
        migrations.AddField(
            model_name="proxmoxapplyjob",
            name="branch_name",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Name of the merged netbox-branching Branch at queue time.",
                max_length=255,
                verbose_name="Branch name",
            ),
        ),
        migrations.AddField(
            model_name="proxmoxapplyjob",
            name="user",
            field=models.ForeignKey(
                blank=True,
                help_text="User associated with the branch merge that queued this run.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
                verbose_name="User",
            ),
        ),
        migrations.AddField(
            model_name="proxmoxapplyjob",
            name="run_uuid",
            field=models.UUIDField(
                default=uuid.uuid4,
                editable=False,
                help_text="Stable run identifier shared with proxbox-api apply logs.",
                unique=True,
                verbose_name="Run UUID",
            ),
        ),
        migrations.AddField(
            model_name="proxmoxapplyjob",
            name="state",
            field=models.CharField(
                choices=[
                    ("queued", "Queued"),
                    ("running", "Running"),
                    ("succeeded", "Succeeded"),
                    ("failed", "Failed"),
                    ("partial", "Partial"),
                ],
                default="queued",
                help_text="Current dry-run executor state.",
                max_length=32,
                verbose_name="State",
            ),
        ),
        migrations.AddField(
            model_name="proxmoxapplyjob",
            name="per_vm_results",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Dry-run result stubs keyed by VM identifier.",
                verbose_name="Per-VM results",
            ),
        ),
        migrations.AddField(
            model_name="proxmoxapplyjob",
            name="started_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name="Started at",
            ),
        ),
        migrations.AddField(
            model_name="proxmoxapplyjob",
            name="finished_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name="Finished at",
            ),
        ),
    ]
