"""Add the plugin-owned per-branch intent model."""

from __future__ import annotations

import netbox.models.deletion
import taggit.managers
import utilities.json
from django.db import migrations, models

from netbox_proxbox.migrations._idempotent_ops import create_model_idempotent


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0089_remove_vm_intent_custom_fields"),
    ]

    operations = [
        create_model_idempotent(
            name="ProxboxBranchIntent",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False
                    ),
                ),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                (
                    "last_updated",
                    models.DateTimeField(auto_now=True, blank=True, null=True),
                ),
                (
                    "custom_field_data",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        encoder=utilities.json.CustomFieldJSONEncoder,
                    ),
                ),
                (
                    "branch_id",
                    models.PositiveBigIntegerField(
                        help_text=(
                            "Soft reference to the netbox-branching Branch primary key."
                        ),
                    ),
                ),
                (
                    "branch_schema_id",
                    models.CharField(
                        help_text=(
                            "Soft reference to the netbox-branching Branch schema ID."
                        ),
                        max_length=8,
                    ),
                ),
                (
                    "apply_to_proxmox",
                    models.BooleanField(
                        default=False,
                        help_text=(
                            "Opt this branch into the NetBox-to-Proxmox intent pipeline."
                        ),
                    ),
                ),
                (
                    "apply_destroy_confirmed",
                    models.BooleanField(
                        default=False,
                        help_text=(
                            "Allow DELETE diffs to produce deletion requests for "
                            "separate authorization."
                        ),
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
                "ordering": ("branch_id",),
                "verbose_name": "Proxbox branch intent",
                "verbose_name_plural": "Proxbox branch intents",
                "constraints": [
                    models.UniqueConstraint(
                        fields=("branch_id", "branch_schema_id"),
                        name="netbox_proxbox_branch_intent_reference_unique",
                    )
                ],
            },
            bases=(netbox.models.deletion.DeleteMixin, models.Model),
        ),
    ]
