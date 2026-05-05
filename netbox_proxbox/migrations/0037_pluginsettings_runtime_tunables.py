from django.db import migrations, models


def _add_column(table: str, column: str, sql_type: str, default: str) -> migrations.RunSQL:
    return migrations.RunSQL(
        sql=(
            f'ALTER TABLE "{table}" '
            f'ADD COLUMN IF NOT EXISTS "{column}" {sql_type} NOT NULL DEFAULT {default};'
        ),
        reverse_sql=(
            f'ALTER TABLE "{table}" DROP COLUMN IF EXISTS "{column}";'
        ),
    )


TABLE = "netbox_proxbox_proxboxpluginsettings"


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0036_add_overwrite_vm_type"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                _add_column(TABLE, "netbox_timeout", "integer", "120"),
                _add_column(TABLE, "netbox_write_concurrency", "smallint", "8"),
                _add_column(TABLE, "proxmox_fetch_concurrency", "smallint", "8"),
                _add_column(TABLE, "netbox_get_cache_max_entries", "integer", "4096"),
                _add_column(TABLE, "netbox_get_cache_max_bytes", "bigint", "52428800"),
                _add_column(TABLE, "backup_batch_size", "smallint", "5"),
                _add_column(TABLE, "backup_batch_delay_ms", "integer", "200"),
                _add_column(TABLE, "debug_cache", "boolean", "FALSE"),
                _add_column(TABLE, "expose_internal_errors", "boolean", "FALSE"),
            ],
            state_operations=[
                migrations.AddField(
                    model_name="proxboxpluginsettings",
                    name="netbox_timeout",
                    field=models.PositiveIntegerField(
                        default=120,
                        verbose_name="NetBox client timeout (seconds)",
                        help_text=(
                            "Timeout for proxbox-api → NetBox HTTP requests. "
                            "Increase when NetBox runs slow large queries."
                        ),
                    ),
                ),
                migrations.AddField(
                    model_name="proxboxpluginsettings",
                    name="netbox_write_concurrency",
                    field=models.PositiveSmallIntegerField(
                        default=8,
                        verbose_name="NetBox write concurrency",
                        help_text=(
                            "Maximum concurrent NetBox write operations (creates/updates) "
                            "used by VM, snapshot, and task-history sync paths."
                        ),
                    ),
                ),
                migrations.AddField(
                    model_name="proxboxpluginsettings",
                    name="proxmox_fetch_concurrency",
                    field=models.PositiveSmallIntegerField(
                        default=8,
                        verbose_name="Proxmox fetch concurrency",
                        help_text=(
                            "Maximum concurrent Proxmox read operations used by backup, "
                            "snapshot, and task-history discovery."
                        ),
                    ),
                ),
                migrations.AddField(
                    model_name="proxboxpluginsettings",
                    name="netbox_get_cache_max_entries",
                    field=models.PositiveIntegerField(
                        default=4096,
                        verbose_name="NetBox GET cache max entries",
                        help_text=(
                            "Maximum number of entries kept in the in-memory NetBox GET "
                            "cache before least-recently-used entries are evicted."
                        ),
                    ),
                ),
                migrations.AddField(
                    model_name="proxboxpluginsettings",
                    name="netbox_get_cache_max_bytes",
                    field=models.PositiveBigIntegerField(
                        default=52_428_800,
                        verbose_name="NetBox GET cache max bytes",
                        help_text=(
                            "Maximum total size in bytes of the in-memory NetBox GET cache. "
                            "Default is 50 MiB."
                        ),
                    ),
                ),
                migrations.AddField(
                    model_name="proxboxpluginsettings",
                    name="backup_batch_size",
                    field=models.PositiveSmallIntegerField(
                        default=5,
                        verbose_name="Backup batch size",
                        help_text=(
                            "Number of VM backup records processed per batch during backup sync."
                        ),
                    ),
                ),
                migrations.AddField(
                    model_name="proxboxpluginsettings",
                    name="backup_batch_delay_ms",
                    field=models.PositiveIntegerField(
                        default=200,
                        verbose_name="Backup batch delay (ms)",
                        help_text=(
                            "Milliseconds to wait between backup batches to throttle "
                            "Proxmox/NetBox load."
                        ),
                    ),
                ),
                migrations.AddField(
                    model_name="proxboxpluginsettings",
                    name="debug_cache",
                    field=models.BooleanField(
                        default=False,
                        verbose_name="Debug cache logging",
                        help_text=(
                            "When enabled, proxbox-api emits verbose log entries for NetBox GET "
                            "cache hits, misses, and evictions. Useful for diagnosing cache behavior."
                        ),
                    ),
                ),
                migrations.AddField(
                    model_name="proxboxpluginsettings",
                    name="expose_internal_errors",
                    field=models.BooleanField(
                        default=False,
                        verbose_name="Expose internal errors",
                        help_text=(
                            "When enabled, proxbox-api includes internal exception details in "
                            "HTTP error responses. Leave disabled in production to avoid leaking "
                            "implementation details."
                        ),
                    ),
                ),
            ],
        ),
    ]
