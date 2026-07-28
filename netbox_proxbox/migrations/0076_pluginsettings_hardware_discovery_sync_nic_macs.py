"""Add the explicit opt-in for physical-NIC MAC reflection."""

from __future__ import annotations

from django.db import migrations, models

from netbox_proxbox.migrations._idempotent_ops import add_field_idempotent


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0075_fastapi_backend_key_target_fingerprint"),
    ]

    operations = [
        add_field_idempotent(
            model_name="proxboxpluginsettings",
            field_name="hardware_discovery_sync_nic_macs",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Opt in to creating native dcim.MACAddress rows and setting "
                    "primary_mac_address for physical node interfaces from "
                    "SSH-discovered hardware facts. Requires SSH-based hardware "
                    "discovery to be enabled. Off by default so upgrades do not "
                    "introduce new MAC writes."
                ),
                verbose_name="Sync physical NIC MAC addresses",
            ),
        ),
    ]
