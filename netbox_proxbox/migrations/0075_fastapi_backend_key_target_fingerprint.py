"""Persist the reviewed trust target for each encrypted FastAPI backend key.

Existing rows intentionally start blank and therefore cannot emit the stored
credential until an operator explicitly resubmits it through the adoption gate.
This avoids silently blessing a mutable IPAddress value during upgrade.
"""

from __future__ import annotations

from django.db import migrations, models

from netbox_proxbox.migrations._idempotent_ops import add_field_idempotent


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0074_proxmoxendpoint_pushed_credential_fingerprint"),
    ]

    operations = [
        add_field_idempotent(
            model_name="fastapiendpoint",
            field_name="backend_key_target_fingerprint",
            field=models.CharField(
                blank=True,
                default="",
                editable=False,
                help_text=(
                    "Internal fingerprint binding the encrypted key to its "
                    "reviewed backend authority and server WebSocket policy."
                ),
                max_length=64,
                verbose_name="Adopted backend-key target fingerprint",
            ),
        ),
    ]
