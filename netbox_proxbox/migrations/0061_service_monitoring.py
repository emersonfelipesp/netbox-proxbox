from __future__ import annotations

import django.core.validators
import django.db.models.deletion
import taggit.managers
import utilities.json
from django.db import migrations, models
from django.utils import timezone

from netbox_proxbox.migrations._idempotent_ops import (
    add_field_idempotent,
    create_model_idempotent,
)


TRIGGER_CHOICES = [
    ("scheduled", "Scheduled"),
    ("on_demand", "On demand"),
]

STATUS_CHOICES = [
    ("pending", "Pending"),
    ("succeeded", "Succeeded"),
    ("failed", "Failed"),
]


def _netbox_model_fields():
    return [
        (
            "id",
            models.BigAutoField(auto_created=True, primary_key=True, serialize=False),
        ),
        ("created", models.DateTimeField(auto_now_add=True, null=True)),
        ("last_updated", models.DateTimeField(auto_now=True, null=True)),
        (
            "custom_field_data",
            models.JSONField(
                blank=True,
                default=dict,
                encoder=utilities.json.CustomFieldJSONEncoder,
            ),
        ),
        (
            "tags",
            taggit.managers.TaggableManager(
                through="extras.TaggedItem",
                to="extras.Tag",
            ),
        ),
    ]


def _service_state_fields():
    return [
        ("unit", models.CharField(db_index=True, max_length=255, verbose_name="Unit")),
        (
            "service_id",
            models.CharField(
                blank=True,
                default="",
                max_length=255,
                verbose_name="Systemd ID",
            ),
        ),
        ("load_state", models.CharField(blank=True, default="", max_length=64)),
        ("active_state", models.CharField(blank=True, default="", max_length=64)),
        ("sub_state", models.CharField(blank=True, default="", max_length=64)),
        ("result", models.CharField(blank=True, default="", max_length=64)),
        ("main_pid", models.PositiveIntegerField(blank=True, null=True)),
        ("exec_main_code", models.IntegerField(blank=True, null=True)),
        ("exec_main_status", models.IntegerField(blank=True, null=True)),
        ("n_restarts", models.PositiveIntegerField(blank=True, null=True)),
        (
            "active_enter_timestamp",
            models.CharField(blank=True, default="", max_length=128),
        ),
        ("unit_file_state", models.CharField(blank=True, default="", max_length=64)),
    ]


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0060_default_guest_os_model"),
    ]

    operations = [
        add_field_idempotent(
            model_name="proxmoxendpoint",
            field_name="service_monitoring_enabled",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Opt in to agentless systemd service monitoring through "
                    "netbox-rpc. Requires Proxmox-side writes enabled, API + SSH "
                    "access, and complete endpoint SSH credentials."
                ),
                verbose_name="Enable service monitoring",
            ),
        ),
        add_field_idempotent(
            model_name="proxmoxendpoint",
            field_name="service_monitoring_interval_minutes",
            field=models.PositiveIntegerField(
                default=5,
                help_text="Polling interval for systemd service monitoring.",
                validators=[
                    django.core.validators.MinValueValidator(1),
                    django.core.validators.MaxValueValidator(1440),
                ],
                verbose_name="Service monitoring interval (minutes)",
            ),
        ),
        add_field_idempotent(
            model_name="proxmoxendpoint",
            field_name="service_monitoring_units",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text=(
                    "List of systemd units to collect. Leave empty to let "
                    "netbox-rpc use its default Proxmox unit set."
                ),
                verbose_name="Service monitoring units",
            ),
        ),
        add_field_idempotent(
            model_name="proxmoxendpoint",
            field_name="service_monitoring_last_success_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name="Service monitoring last success",
            ),
        ),
        add_field_idempotent(
            model_name="proxmoxendpoint",
            field_name="service_monitoring_last_status",
            field=models.CharField(
                blank=True,
                default="",
                max_length=64,
                verbose_name="Service monitoring last status",
            ),
        ),
        add_field_idempotent(
            model_name="proxmoxendpoint",
            field_name="service_monitoring_last_error",
            field=models.TextField(
                blank=True,
                default="",
                verbose_name="Service monitoring last error",
            ),
        ),
        create_model_idempotent(
            name="ProxmoxServiceCollection",
            fields=[
                *_netbox_model_fields(),
                (
                    "endpoint",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="service_collections",
                        to="netbox_proxbox.proxmoxendpoint",
                        verbose_name="Proxmox endpoint",
                    ),
                ),
                (
                    "collected_at",
                    models.DateTimeField(
                        default=timezone.now,
                        verbose_name="Collected at",
                    ),
                ),
                ("reachable", models.BooleanField(default=False, verbose_name="Reachable")),
                (
                    "trigger",
                    models.CharField(
                        choices=TRIGGER_CHOICES,
                        default="scheduled",
                        max_length=16,
                        verbose_name="Trigger",
                    ),
                ),
                (
                    "duration_ms",
                    models.PositiveIntegerField(
                        blank=True,
                        null=True,
                        verbose_name="Duration (ms)",
                    ),
                ),
                (
                    "error_message",
                    models.TextField(
                        blank=True,
                        default="",
                        verbose_name="Error message",
                    ),
                ),
                (
                    "rpc_execution_id",
                    models.PositiveBigIntegerField(
                        blank=True,
                        db_index=True,
                        null=True,
                        verbose_name="RPC execution ID",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=STATUS_CHOICES,
                        db_index=True,
                        default="pending",
                        max_length=16,
                        verbose_name="Status",
                    ),
                ),
            ],
            options={
                "verbose_name": "Proxmox service collection",
                "verbose_name_plural": "Proxmox service collections",
                "ordering": ("-collected_at", "-pk"),
            },
        ),
        create_model_idempotent(
            name="ProxmoxServiceSample",
            fields=[
                *_netbox_model_fields(),
                (
                    "collection",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="samples",
                        to="netbox_proxbox.proxmoxservicecollection",
                        verbose_name="Service collection",
                    ),
                ),
                *_service_state_fields(),
            ],
            options={
                "verbose_name": "Proxmox service sample",
                "verbose_name_plural": "Proxmox service samples",
                "ordering": ("collection", "unit"),
                "unique_together": {("collection", "unit")},
            },
        ),
        create_model_idempotent(
            name="ProxmoxServiceStatus",
            fields=[
                *_netbox_model_fields(),
                (
                    "endpoint",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="service_statuses",
                        to="netbox_proxbox.proxmoxendpoint",
                        verbose_name="Proxmox endpoint",
                    ),
                ),
                *_service_state_fields(),
                ("last_seen_at", models.DateTimeField(verbose_name="Last seen at")),
                ("is_healthy", models.BooleanField(default=False, verbose_name="Healthy")),
                (
                    "expected_active",
                    models.BooleanField(
                        default=True,
                        verbose_name="Expected active",
                    ),
                ),
            ],
            options={
                "verbose_name": "Proxmox service status",
                "verbose_name_plural": "Proxmox service statuses",
                "ordering": ("endpoint", "unit"),
                "unique_together": {("endpoint", "unit")},
            },
        ),
    ]
