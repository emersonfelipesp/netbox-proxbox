"""Migration 0040: add enabled field to all endpoint models."""
from __future__ import annotations

from django.db import migrations, models

from netbox_proxbox.migrations._idempotent_ops import add_field_idempotent


class Migration(migrations.Migration):

    dependencies = [
        ("netbox_proxbox", "0039_pve_firewall"),
    ]

    operations = [
        add_field_idempotent(
            "proxmoxendpoint",
            "enabled",
            models.BooleanField(default=True),
        ),
        add_field_idempotent(
            "netboxendpoint",
            "enabled",
            models.BooleanField(default=True),
        ),
        add_field_idempotent(
            "fastapiendpoint",
            "enabled",
            models.BooleanField(default=True),
        ),
    ]
