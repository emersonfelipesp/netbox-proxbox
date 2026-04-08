"""Add operational settings fields to ProxboxPluginSettings."""

from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0024_add_backend_log_file_path"),
    ]

    operations = [
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
    ]
