"""Add deletion authorization settings for Sub-PR I.

Idempotent: every ``AddField`` is wrapped through ``add_field_idempotent``
so reporter-style installs whose legacy lineage already added these columns
do not abort with ``DuplicateColumn``.
"""

from __future__ import annotations

import django.core.validators
from django.db import migrations, models

from netbox_proxbox.migrations._idempotent_ops import add_field_idempotent


class Migration(migrations.Migration):

    dependencies = [
        ("netbox_proxbox", "0041_deletion_request_full"),
    ]

    operations = [
        add_field_idempotent(
            model_name="proxboxpluginsettings",
            field_name="intent_apply_authorization_self_approve_allowed",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "When enabled, the user who requested a Proxmox deletion may also approve "
                    "the DeletionRequest. Leave disabled for four-eyes authorization."
                ),
                verbose_name="Allow deletion request self-approval",
            ),
        ),
        add_field_idempotent(
            model_name="proxboxpluginsettings",
            field_name="intent_deletion_request_ttl_days",
            field=models.IntegerField(
                default=7,
                help_text=(
                    "Pending DeletionRequests older than this many days are auto-rejected "
                    "and the pending-deletion tag is removed from Proxmox best-effort."
                ),
                validators=[django.core.validators.MinValueValidator(1)],
                verbose_name="Deletion request TTL (days)",
            ),
        ),
    ]
