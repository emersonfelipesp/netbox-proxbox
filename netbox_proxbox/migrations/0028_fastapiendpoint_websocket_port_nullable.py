"""Make FastAPIEndpoint.websocket_port nullable and default to None.

Existing rows with the old hardcoded default of 8800 are reset to NULL so
the URL-builder falls back to the HTTP port, matching user expectation that
websocket_port inherits from port unless explicitly overridden.
"""

import django.core.validators
from django.db import migrations, models


def clear_legacy_websocket_port(apps, schema_editor):
    """Set websocket_port=NULL for rows that still carry the old hardcoded default (8800)."""
    FastAPIEndpoint = apps.get_model("netbox_proxbox", "FastAPIEndpoint")
    FastAPIEndpoint.objects.filter(websocket_port=8800).update(websocket_port=None)


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0027_vmtaskhistory_pstart_to_biginteger"),
    ]

    operations = [
        # 1. Widen the column to allow NULL before clearing legacy values.
        migrations.AlterField(
            model_name="fastapiendpoint",
            name="websocket_port",
            field=models.PositiveIntegerField(
                blank=True,
                null=True,
                default=None,
                validators=[
                    django.core.validators.MinValueValidator(1),
                    django.core.validators.MaxValueValidator(65535),
                ],
                verbose_name="WebSocket port",
                help_text=(
                    "Port used for WebSocket connectivity. "
                    "Leave blank to use the same port as the HTTP endpoint."
                ),
            ),
        ),
        # 2. Reset existing rows that still have the hardcoded 8800 default.
        migrations.RunPython(
            clear_legacy_websocket_port,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
