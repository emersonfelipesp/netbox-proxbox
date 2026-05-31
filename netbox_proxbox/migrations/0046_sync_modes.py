"""Add per-resource sync mode controls."""

from __future__ import annotations

from django.db import migrations, models

from netbox_proxbox.migrations._idempotent_ops import add_field_idempotent


SYNC_MODE_CHOICES = [
    ("always", "Always"),
    ("bootstrap_only", "Bootstrap only"),
    ("disabled", "Disabled"),
]

SYNC_MODE_FIELDS = (
    "sync_mode_vm",
    "sync_mode_vm_template",
    "sync_mode_cluster",
    "sync_mode_node",
    "sync_mode_storage",
    "sync_mode_ip_address",
)

SYNC_MODE_VERBOSE_NAMES = {
    "sync_mode_vm": "VM sync mode",
    "sync_mode_vm_template": "VM template sync mode",
    "sync_mode_cluster": "Cluster sync mode",
    "sync_mode_node": "Node sync mode",
    "sync_mode_storage": "Storage sync mode",
    "sync_mode_ip_address": "IP address sync mode",
}

SYNC_MODE_SETTINGS_HELP = {
    "sync_mode_vm": (
        "Controls non-template VM synchronization: always sync, create once "
        "and tag bootstrap-only, or skip entirely."
    ),
    "sync_mode_vm_template": (
        "Controls Proxmox template VM synchronization separately from normal VMs."
    ),
    "sync_mode_cluster": "Controls synchronization of Proxmox cluster tracking rows.",
    "sync_mode_node": "Controls synchronization of Proxmox node tracking rows.",
    "sync_mode_storage": "Controls synchronization of Proxmox storage inventory.",
    "sync_mode_ip_address": (
        "Controls synchronization of IP addresses discovered from VM interfaces."
    ),
}


def _settings_field(name: str) -> models.CharField:
    return models.CharField(
        max_length=16,
        choices=SYNC_MODE_CHOICES,
        default="always",
        verbose_name=SYNC_MODE_VERBOSE_NAMES[name],
        help_text=SYNC_MODE_SETTINGS_HELP[name],
    )


def _endpoint_field(name: str) -> models.CharField:
    return models.CharField(
        max_length=16,
        choices=SYNC_MODE_CHOICES,
        null=True,
        blank=True,
        verbose_name=SYNC_MODE_VERBOSE_NAMES[name],
        help_text=(
            "Per-endpoint override for the global Proxbox sync mode. "
            "Leave blank to inherit."
        ),
    )


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0045_repair_pbs_pdm_endpoint_enabled"),
    ]

    operations = [
        *[
            add_field_idempotent(
                model_name="proxboxpluginsettings",
                field_name=name,
                field=_settings_field(name),
            )
            for name in SYNC_MODE_FIELDS
        ],
        *[
            add_field_idempotent(
                model_name="proxmoxendpoint",
                field_name=name,
                field=_endpoint_field(name),
            )
            for name in SYNC_MODE_FIELDS
        ],
    ]
