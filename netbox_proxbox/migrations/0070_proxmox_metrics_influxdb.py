import django.core.validators
import django.db.models.deletion
import taggit.managers
import utilities.json
from django.db import migrations, models

from netbox_proxbox.migrations._idempotent_ops import create_model_idempotent


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


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0069_sync_state_relation_fk_cleanup"),
    ]

    operations = [
        create_model_idempotent(
            name="ProxmoxMetricsInfluxDB",
            fields=[
                *_netbox_model_fields(),
                (
                    "name",
                    models.CharField(
                        default="default",
                        help_text="Operator label for this InfluxDB metrics endpoint.",
                        max_length=100,
                        verbose_name="Name",
                    ),
                ),
                (
                    "influx_url",
                    models.URLField(
                        help_text="Base URL for InfluxDB, for example https://influxdb.example:8086.",
                        max_length=255,
                        verbose_name="InfluxDB URL",
                    ),
                ),
                (
                    "org",
                    models.CharField(
                        default="nmulticloud",
                        max_length=128,
                        verbose_name="InfluxDB organization",
                    ),
                ),
                (
                    "bucket",
                    models.CharField(
                        default="proxmox",
                        max_length=128,
                        verbose_name="InfluxDB bucket",
                    ),
                ),
                (
                    "measurement_prefix",
                    models.CharField(
                        blank=True,
                        help_text="Optional Flux measurement prefix used by the Proxmox metrics writer.",
                        max_length=64,
                        verbose_name="Measurement prefix",
                    ),
                ),
                (
                    "query_token_secret_ref",
                    models.CharField(
                        help_text="netbox-nms ObservabilitySecret reference, not plaintext.",
                        max_length=80,
                        validators=[
                            django.core.validators.RegexValidator(
                                regex=(
                                    "^nms-secret:[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-"
                                    "[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                                    "[0-9a-fA-F]{12}$"
                                )
                            )
                        ],
                        verbose_name="Query token secret reference",
                    ),
                ),
                (
                    "writer_token_secret_ref",
                    models.CharField(
                        blank=True,
                        help_text="Optional PVE writer token reference for configuring Proxmox.",
                        max_length=80,
                        validators=[
                            django.core.validators.RegexValidator(
                                regex=(
                                    "^nms-secret:[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-"
                                    "[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                                    "[0-9a-fA-F]{12}$"
                                )
                            )
                        ],
                        verbose_name="Writer token secret reference",
                    ),
                ),
                (
                    "verify_tls",
                    models.BooleanField(
                        default=True,
                        help_text="Verify the InfluxDB server certificate when querying metrics.",
                        verbose_name="Verify TLS",
                    ),
                ),
                (
                    "enabled",
                    models.BooleanField(
                        default=True,
                        help_text="Disabled mappings are inventory-only and must not be queried.",
                        verbose_name="Enabled",
                    ),
                ),
                ("comments", models.TextField(blank=True)),
                (
                    "endpoint",
                    models.ForeignKey(
                        help_text="Proxmox endpoint whose cluster writes to this InfluxDB server.",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="metrics_influxdb_endpoints",
                        to="netbox_proxbox.proxmoxendpoint",
                        verbose_name="Proxmox endpoint",
                    ),
                ),
                (
                    "proxmox_cluster",
                    models.ForeignKey(
                        help_text="Proxmox cluster associated with this InfluxDB bucket.",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="metrics_influxdb_endpoints",
                        to="netbox_proxbox.proxmoxcluster",
                        verbose_name="Proxmox cluster",
                    ),
                ),
            ],
            options={
                "verbose_name": "Proxmox InfluxDB metrics endpoint",
                "verbose_name_plural": "Proxmox InfluxDB metrics endpoints",
                "ordering": ("endpoint", "proxmox_cluster", "name"),
                "constraints": [
                    models.UniqueConstraint(
                        fields=("proxmox_cluster", "name"),
                        name="netbox_proxbox_metrics_influxdb_unique_cluster_name",
                    )
                ],
            },
        ),
    ]
