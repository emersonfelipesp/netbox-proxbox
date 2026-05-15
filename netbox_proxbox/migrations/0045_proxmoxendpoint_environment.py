"""Add operator-selected environment field to ProxmoxEndpoint."""

from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("netbox_proxbox", "0044_cloud_image_template"),
    ]

    operations = [
        migrations.AddField(
            model_name="proxmoxendpoint",
            name="environment",
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
