"""Add plaintext password warning setting for Cloud-Init intent payloads.

Idempotent: the ``AddField`` is wrapped through ``add_field_idempotent`` so
reporter-style installs whose legacy lineage already added this column do
not abort with ``DuplicateColumn``.
"""

from __future__ import annotations

from django.db import migrations, models

from netbox_proxbox.migrations._idempotent_ops import add_field_idempotent


class Migration(migrations.Migration):

    dependencies = [
        ("netbox_proxbox", "0042_pluginsettings_self_approve"),
    ]

    operations = [
        add_field_idempotent(
            model_name="proxboxpluginsettings",
            field_name="intent_warn_plaintext_password",
            field=models.BooleanField(
                default=True,
                help_text=(
                    "When enabled, the intent merge validator emits a warning if "
                    "cloud_init_user_data contains a plaintext password line."
                ),
                verbose_name="Warn on plaintext cloud-init passwords",
            ),
        ),
    ]
