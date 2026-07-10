"""Add per-endpoint netbox-rpc enablement override to ProxmoxEndpoint."""

from __future__ import annotations

from django.db import migrations, models

from netbox_proxbox.migrations._idempotent_ops import add_field_idempotent


def _rpc_enabled_field() -> models.BooleanField:
    return models.BooleanField(
        null=True,
        blank=True,
        verbose_name="RPC enabled",
        help_text=(
            "Per-endpoint override for netbox-rpc operations against this Proxmox "
            "endpoint. Leave blank to inherit the global netbox-rpc setting; set "
            "explicitly to override it (per-endpoint wins)."
        ),
    )


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0058_encrypt_primary_endpoint_secrets"),
    ]

    operations = [
        add_field_idempotent(
            model_name="proxmoxendpoint",
            field_name="rpc_enabled",
            field=_rpc_enabled_field(),
        ),
    ]
