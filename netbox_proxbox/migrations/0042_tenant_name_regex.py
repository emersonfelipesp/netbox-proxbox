from django.db import migrations, models


SETTINGS_TABLE = "netbox_proxbox_proxboxpluginsettings"
ENDPOINT_TABLE = "netbox_proxbox_proxmoxendpoint"


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0041_run_proxmox_action_permission"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql=(
                        f'ALTER TABLE "{SETTINGS_TABLE}" '
                        f'ADD COLUMN IF NOT EXISTS "enable_tenant_name_regex" '
                        f'boolean NOT NULL DEFAULT FALSE;'
                    ),
                    reverse_sql=(
                        f'ALTER TABLE "{SETTINGS_TABLE}" '
                        f'DROP COLUMN IF EXISTS "enable_tenant_name_regex";'
                    ),
                ),
                migrations.RunSQL(
                    sql=(
                        f'ALTER TABLE "{SETTINGS_TABLE}" '
                        f'ADD COLUMN IF NOT EXISTS "tenant_name_regex_rules" '
                        f"jsonb NOT NULL DEFAULT '[]'::jsonb;"
                    ),
                    reverse_sql=(
                        f'ALTER TABLE "{SETTINGS_TABLE}" '
                        f'DROP COLUMN IF EXISTS "tenant_name_regex_rules";'
                    ),
                ),
                migrations.RunSQL(
                    sql=(
                        f'ALTER TABLE "{ENDPOINT_TABLE}" '
                        f'ADD COLUMN IF NOT EXISTS "enable_tenant_name_regex" boolean NULL;'
                    ),
                    reverse_sql=(
                        f'ALTER TABLE "{ENDPOINT_TABLE}" '
                        f'DROP COLUMN IF EXISTS "enable_tenant_name_regex";'
                    ),
                ),
                migrations.RunSQL(
                    sql=(
                        f'ALTER TABLE "{ENDPOINT_TABLE}" '
                        f'ADD COLUMN IF NOT EXISTS "tenant_name_regex_rules" jsonb NULL;'
                    ),
                    reverse_sql=(
                        f'ALTER TABLE "{ENDPOINT_TABLE}" '
                        f'DROP COLUMN IF EXISTS "tenant_name_regex_rules";'
                    ),
                ),
            ],
            state_operations=[
                migrations.AddField(
                    model_name="proxboxpluginsettings",
                    name="enable_tenant_name_regex",
                    field=models.BooleanField(
                        default=False,
                        verbose_name="Enable tenant assignment by VM-name regex",
                        help_text=(
                            "When enabled, sync resolves a NetBox Tenant for VMs by matching the "
                            "VM name against the rules below. Disabled by default. Existing "
                            "tenant assignments are never overwritten."
                        ),
                    ),
                ),
                migrations.AddField(
                    model_name="proxboxpluginsettings",
                    name="tenant_name_regex_rules",
                    field=models.JSONField(
                        blank=True,
                        default=list,
                        verbose_name="Tenant name regex rules",
                        help_text=(
                            "Ordered list of {pattern, tenant_slug, [label]} dicts. First match "
                            "wins; specificity-first ordering is recommended (e.g. '^cust-acme-' "
                            "before '^cust-'). Patterns are compiled and tenant slugs are verified "
                            "at save time."
                        ),
                    ),
                ),
                migrations.AddField(
                    model_name="proxmoxendpoint",
                    name="enable_tenant_name_regex",
                    field=models.BooleanField(
                        blank=True,
                        null=True,
                        verbose_name="Enable tenant regex (override)",
                        help_text=(
                            "Per-endpoint override for the global tenant-regex toggle. "
                            "Leave blank to inherit."
                        ),
                    ),
                ),
                migrations.AddField(
                    model_name="proxmoxendpoint",
                    name="tenant_name_regex_rules",
                    field=models.JSONField(
                        blank=True,
                        null=True,
                        default=None,
                        verbose_name="Tenant regex rules (override)",
                        help_text=(
                            "Per-endpoint override for the global rule list. Leave null to "
                            "inherit. When set (even to an empty list), replaces the global "
                            "list for this endpoint."
                        ),
                    ),
                ),
            ],
        ),
    ]
