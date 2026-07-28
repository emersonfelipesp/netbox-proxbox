"""Add bounded Ceph task and durable run timing settings."""

from __future__ import annotations

import decimal

import django.core.validators
from django.db import migrations, models

from netbox_proxbox.migrations._idempotent_ops import add_field_idempotent


class Migration(migrations.Migration):
    dependencies = [
        (
            "netbox_proxbox",
            "0076_pluginsettings_hardware_discovery_sync_nic_macs",
        ),
    ]

    operations = [
        add_field_idempotent(
            model_name="proxboxpluginsettings",
            field_name="ceph_task_timeout",
            field=models.DecimalField(
                decimal_places=2,
                default=decimal.Decimal("300.00"),
                help_text=(
                    "Maximum time proxbox-api waits for a submitted Proxmox Ceph "
                    "task to reach a terminal state."
                ),
                max_digits=6,
                validators=[
                    django.core.validators.MinValueValidator(decimal.Decimal("1.00")),
                    django.core.validators.MaxValueValidator(
                        decimal.Decimal("3600.00")
                    ),
                ],
                verbose_name="Ceph task timeout (seconds)",
            ),
        ),
        add_field_idempotent(
            model_name="proxboxpluginsettings",
            field_name="ceph_task_poll_interval",
            field=models.DecimalField(
                decimal_places=2,
                default=decimal.Decimal("1.00"),
                help_text=(
                    "Delay between proxbox-api status checks for an active Proxmox "
                    "Ceph task. This interval must not exceed the task timeout."
                ),
                max_digits=6,
                validators=[
                    django.core.validators.MinValueValidator(decimal.Decimal("0.10")),
                    django.core.validators.MaxValueValidator(decimal.Decimal("60.00")),
                ],
                verbose_name="Ceph task polling interval (seconds)",
            ),
        ),
        add_field_idempotent(
            model_name="proxboxpluginsettings",
            field_name="ceph_run_lease_seconds",
            field=models.DecimalField(
                decimal_places=2,
                default=decimal.Decimal("360.00"),
                help_text=(
                    "Durable lease duration captured when a Ceph operation run starts. "
                    "proxbox-api renews it independently from provider task polling."
                ),
                max_digits=6,
                validators=[
                    django.core.validators.MinValueValidator(decimal.Decimal("1.00")),
                    django.core.validators.MaxValueValidator(
                        decimal.Decimal("3600.00")
                    ),
                ],
                verbose_name="Ceph operation lease (seconds)",
            ),
        ),
    ]
