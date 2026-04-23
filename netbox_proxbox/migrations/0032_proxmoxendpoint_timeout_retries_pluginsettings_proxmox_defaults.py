from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0031_proxmoxendpoint_site_tenant"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql='ALTER TABLE "netbox_proxbox_proxmoxendpoint" ADD COLUMN IF NOT EXISTS "timeout" integer NULL;',
                    reverse_sql='ALTER TABLE "netbox_proxbox_proxmoxendpoint" DROP COLUMN IF EXISTS "timeout";',
                ),
                migrations.RunSQL(
                    sql='ALTER TABLE "netbox_proxbox_proxmoxendpoint" ADD COLUMN IF NOT EXISTS "max_retries" smallint NULL;',
                    reverse_sql='ALTER TABLE "netbox_proxbox_proxmoxendpoint" DROP COLUMN IF EXISTS "max_retries";',
                ),
                migrations.RunSQL(
                    sql='ALTER TABLE "netbox_proxbox_proxmoxendpoint" ADD COLUMN IF NOT EXISTS "retry_backoff" numeric(5, 2) NULL;',
                    reverse_sql='ALTER TABLE "netbox_proxbox_proxmoxendpoint" DROP COLUMN IF EXISTS "retry_backoff";',
                ),
                migrations.RunSQL(
                    sql='ALTER TABLE "netbox_proxbox_proxboxpluginsettings" ADD COLUMN IF NOT EXISTS "proxmox_timeout" integer NOT NULL DEFAULT 5;',
                    reverse_sql='ALTER TABLE "netbox_proxbox_proxboxpluginsettings" DROP COLUMN IF EXISTS "proxmox_timeout";',
                ),
                migrations.RunSQL(
                    sql='ALTER TABLE "netbox_proxbox_proxboxpluginsettings" ADD COLUMN IF NOT EXISTS "proxmox_max_retries" smallint NOT NULL DEFAULT 0;',
                    reverse_sql='ALTER TABLE "netbox_proxbox_proxboxpluginsettings" DROP COLUMN IF EXISTS "proxmox_max_retries";',
                ),
                migrations.RunSQL(
                    sql='ALTER TABLE "netbox_proxbox_proxboxpluginsettings" ADD COLUMN IF NOT EXISTS "proxmox_retry_backoff" numeric(5, 2) NOT NULL DEFAULT 0.50;',
                    reverse_sql='ALTER TABLE "netbox_proxbox_proxboxpluginsettings" DROP COLUMN IF EXISTS "proxmox_retry_backoff";',
                ),
            ],
            state_operations=[
                migrations.AddField(
                    model_name="proxmoxendpoint",
                    name="timeout",
                    field=models.PositiveIntegerField(
                        blank=True,
                        null=True,
                        verbose_name="Timeout (seconds)",
                        help_text="Per-endpoint API request timeout in seconds. Leave blank to use the global default.",
                    ),
                ),
                migrations.AddField(
                    model_name="proxmoxendpoint",
                    name="max_retries",
                    field=models.PositiveSmallIntegerField(
                        blank=True,
                        null=True,
                        verbose_name="Max retries",
                        help_text="Per-endpoint maximum retry attempts for transient failures (GET/HEAD only). Leave blank to use the global default.",
                    ),
                ),
                migrations.AddField(
                    model_name="proxmoxendpoint",
                    name="retry_backoff",
                    field=models.DecimalField(
                        max_digits=5,
                        decimal_places=2,
                        blank=True,
                        null=True,
                        verbose_name="Retry back-off (seconds)",
                        help_text="Per-endpoint exponential back-off base delay in seconds between retries. Leave blank to use the global default.",
                    ),
                ),
                migrations.AddField(
                    model_name="proxboxpluginsettings",
                    name="proxmox_timeout",
                    field=models.PositiveIntegerField(
                        default=5,
                        verbose_name="Proxmox API timeout (seconds)",
                        help_text="Default timeout in seconds for Proxmox API requests. Individual endpoints can override this value.",
                    ),
                ),
                migrations.AddField(
                    model_name="proxboxpluginsettings",
                    name="proxmox_max_retries",
                    field=models.PositiveSmallIntegerField(
                        default=0,
                        verbose_name="Proxmox max retries",
                        help_text="Default maximum retry attempts for transient Proxmox API failures (GET/HEAD only). Individual endpoints can override this value.",
                    ),
                ),
                migrations.AddField(
                    model_name="proxboxpluginsettings",
                    name="proxmox_retry_backoff",
                    field=models.DecimalField(
                        max_digits=5,
                        decimal_places=2,
                        default=Decimal("0.50"),
                        verbose_name="Proxmox retry back-off (seconds)",
                        help_text="Default exponential back-off base delay in seconds between Proxmox retries. Individual endpoints can override this value.",
                    ),
                ),
            ],
        ),
    ]
