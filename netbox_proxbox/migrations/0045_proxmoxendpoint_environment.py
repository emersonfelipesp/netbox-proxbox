"""Add operator-selected environment field to ProxmoxEndpoint.

Idempotent: the ``AddField`` is wrapped through ``add_field_idempotent`` so
reporter-style installs whose legacy lineage already added this column do
not abort with ``DuplicateColumn``.
"""

from __future__ import annotations

from django.db import migrations, models

from netbox_proxbox.migrations._idempotent_ops import add_field_idempotent


class Migration(migrations.Migration):

    dependencies = [
        ("netbox_proxbox", "0044_cloud_image_template"),
    ]

    operations = [
        add_field_idempotent(
            model_name="proxmoxendpoint",
            field_name="environment",
            field=models.CharField(
                blank=True,
                choices=[
                    ("production", "Production"),
                    ("staging", "Staging"),
                    ("development", "Development"),
                    ("homologation", "Homologation"),
                    ("testing", "Testing"),
                    ("lab", "Lab"),
                ],
                help_text=(
                    "Operator-selected lifecycle stage (e.g. production, development, "
                    "homologation). Manual classification only; never written by sync."
                ),
                max_length=32,
                null=True,
                verbose_name="Environment",
            ),
        ),
    ]
