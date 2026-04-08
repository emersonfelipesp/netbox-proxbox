"""Squashed migration: 0022-0026 FastAPI tokens, settings, and constraint conversions."""

import logging
import secrets
from decimal import Decimal

from django.db import migrations, models
import taggit.managers
import utilities.json

logger = logging.getLogger(__name__)


def populate_fastapi_tokens(apps, schema_editor):
    """Generate tokens for FastAPIEndpoint objects with empty tokens."""
    FastAPIEndpoint = apps.get_model("netbox_proxbox", "FastAPIEndpoint")

    for endpoint in FastAPIEndpoint.objects.filter(token=""):
        logger.info("Generating token for FastAPIEndpoint %s", endpoint.pk)
        endpoint.token = secrets.token_urlsafe(48)
        endpoint.save()
        logger.info(
            "FastAPIEndpoint %s token generated (registration will be retried on save signal)",
            endpoint.pk,
        )


class Migration(migrations.Migration):

    replaces = [
        ("netbox_proxbox", "0022_populate_fastapi_tokens"),
        ("netbox_proxbox", "0023_add_ssrf_settings"),
        ("netbox_proxbox", "0024_add_backend_log_file_path"),
        ("netbox_proxbox", "0025_add_operational_settings"),
        ("netbox_proxbox", "0026_convert_unique_together_to_constraints"),
    ]

    dependencies = [
        ("netbox_proxbox", "0021_backuproutine_tags_replication_tags_and_more"),
        ("extras", "0134_owner"),
    ]

    operations = [
        # 0022: Populate FastAPI tokens
        migrations.RunPython(populate_fastapi_tokens),
        # 0023: Add SSRF settings
        migrations.AddField(
            model_name="proxboxpluginsettings",
            name="ssrf_protection_enabled",
            field=models.BooleanField(
                default=True,
                help_text="When enabled, validates that Proxmox/NetBox/FastAPI endpoints do not point to reserved or internal IP addresses. Disable only in trusted environments.",
                verbose_name="Enable SSRF protection",
            ),
        ),
        migrations.AddField(
            model_name="proxboxpluginsettings",
            name="allow_private_ips",
            field=models.BooleanField(
                default=True,
                help_text="When enabled, allows endpoints with private IP addresses (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16). Recommended for on-premises deployments.",
                verbose_name="Allow private IP addresses",
            ),
        ),
        migrations.AddField(
            model_name="proxboxpluginsettings",
            name="additional_allowed_ip_ranges",
            field=models.TextField(
                blank=True,
                default="",
                help_text="One CIDR range per line (e.g., 10.30.0.0/16). IPs in these ranges are always allowed, regardless of other SSRF settings.",
                verbose_name="Additional allowed IP CIDR ranges",
            ),
        ),
        migrations.AddField(
            model_name="proxboxpluginsettings",
            name="explicitly_blocked_ip_ranges",
            field=models.TextField(
                blank=True,
                default="",
                help_text="One CIDR range per line. IPs in these ranges are always blocked, even if they match allowed ranges above.",
                verbose_name="Explicitly blocked IP CIDR ranges",
            ),
        ),
        # 0024: Add backend log file path
        migrations.AddField(
            model_name="proxboxpluginsettings",
            name="backend_log_file_path",
            field=models.CharField(
                default="/var/log/proxbox.log",
                help_text=(
                    "Absolute file path for proxbox-api rotated log archive output "
                    "(for example /var/log/proxbox.log). Changes apply after proxbox-api restart."
                ),
                max_length=255,
                verbose_name="Backend log file path",
            ),
        ),
        # 0025: Add operational settings
        migrations.AddField(
            model_name="proxboxpluginsettings",
            name="netbox_max_concurrent",
            field=models.PositiveSmallIntegerField(
                default=1,
                help_text="Maximum number of simultaneous in-flight requests to the NetBox API (semaphore cap). Increase carefully — PostgreSQL pool may exhaust.",
                verbose_name="NetBox max concurrent requests",
            ),
        ),
        migrations.AddField(
            model_name="proxboxpluginsettings",
            name="netbox_max_retries",
            field=models.PositiveSmallIntegerField(
                default=5,
                help_text="Maximum retry attempts for transient NetBox API failures.",
                verbose_name="NetBox max retries",
            ),
        ),
        migrations.AddField(
            model_name="proxboxpluginsettings",
            name="netbox_retry_delay",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("2.00"),
                help_text="Base delay in seconds for exponential back-off between retries.",
                max_digits=5,
                verbose_name="NetBox retry delay (seconds)",
            ),
        ),
        migrations.AddField(
            model_name="proxboxpluginsettings",
            name="netbox_get_cache_ttl",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("60.00"),
                help_text="How long to cache NetBox GET responses in memory. Set to 0 to disable caching.",
                max_digits=7,
                verbose_name="NetBox GET cache TTL (seconds)",
            ),
        ),
        migrations.AddField(
            model_name="proxboxpluginsettings",
            name="bulk_batch_size",
            field=models.PositiveSmallIntegerField(
                default=50,
                help_text="Number of records per batch in bulk create/update operations.",
                verbose_name="Bulk batch size",
            ),
        ),
        migrations.AddField(
            model_name="proxboxpluginsettings",
            name="bulk_batch_delay_ms",
            field=models.PositiveIntegerField(
                default=500,
                help_text="Milliseconds to wait between bulk batches to avoid overwhelming NetBox.",
                verbose_name="Bulk batch delay (ms)",
            ),
        ),
        migrations.AddField(
            model_name="proxboxpluginsettings",
            name="vm_sync_max_concurrency",
            field=models.PositiveSmallIntegerField(
                default=4,
                help_text="Maximum number of VMs synced in parallel during a full update.",
                verbose_name="VM sync max concurrency",
            ),
        ),
        migrations.AddField(
            model_name="proxboxpluginsettings",
            name="custom_fields_request_delay",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                help_text="Optional sleep between custom-field API operations to throttle requests.",
                max_digits=5,
                verbose_name="Custom fields request delay (seconds)",
            ),
        ),
        # 0026: Convert unique_together to constraints
        migrations.RunSQL(
            sql=[
                "ALTER TABLE netbox_proxbox_proxmoxstorage DROP CONSTRAINT IF EXISTS netbox_proxbox_proxmoxstorage_cluster_id_name_key;",
                "ALTER TABLE netbox_proxbox_proxmoxstoragevirtualdisk DROP CONSTRAINT IF EXISTS netbox_proxbox_proxmoxstor_proxmox_s_virtual__key;",
                "ALTER TABLE netbox_proxbox_vmbackup DROP CONSTRAINT IF EXISTS netbox_proxbox_vmbackup_storage_virtual_machi_key;",
                "ALTER TABLE netbox_proxbox_vmsnapshot DROP CONSTRAINT IF EXISTS netbox_proxbox_vmsnapshot_vmid_name_node_key;",
            ],
            reverse_sql=migrations.RunSQL.noop,
            state_operations=[],
        ),
        migrations.AddConstraint(
            model_name="proxmoxstorage",
            constraint=models.UniqueConstraint(
                fields=("cluster", "name"),
                name="unique_proxmox_storage_cluster_name",
            ),
        ),
        migrations.AddConstraint(
            model_name="proxmoxstoragevirtualdisk",
            constraint=models.UniqueConstraint(
                fields=("proxmox_storage", "virtual_disk"),
                name="unique_proxmox_storage_virtual_disk",
            ),
        ),
        migrations.AddConstraint(
            model_name="vmbackup",
            constraint=models.UniqueConstraint(
                fields=(
                    "storage",
                    "virtual_machine",
                    "subtype",
                    "format",
                    "volume_id",
                    "vmid",
                ),
                name="unique_vm_backup_fields",
            ),
        ),
        migrations.AddConstraint(
            model_name="vmsnapshot",
            constraint=models.UniqueConstraint(
                fields=("vmid", "name", "node"),
                name="unique_vm_snapshot_vmid_name_node",
            ),
        ),
    ]
