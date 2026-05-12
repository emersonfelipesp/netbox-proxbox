"""Add branching-integration fields to ``ProxboxPluginSettings``.

Issue #370 (umbrella): proxbox-api ↔ netbox-branching integration.

Phase 2 (Proxmox → NetBox auto-branch) needs three operator-tunable knobs:

- ``branching_enabled`` — master switch for per-job branch create/merge.
- ``branch_name_prefix`` — prefix used when auto-creating branches.
- ``branch_on_conflict`` — policy on merge conflicts (``fail`` / ``acknowledge``).

Phase 3 (NetBox → Proxmox intent direction, tracked under #377) reserves the
schema for three additional fields so the migration is single-shot:

- ``netbox_to_proxmox_enabled`` — master flag, off by default.
- ``netbox_to_proxmox_typed_confirmation`` — typed phrase gate.
- ``apply_destroy_confirmed`` — destroy-direction master flag.

Follows the production-safe ``SeparateDatabaseAndState`` + ``IF NOT EXISTS``
pattern established by migration ``0037_pluginsettings_runtime_tunables`` so
re-running on partially-upgraded installs is idempotent.
"""

from django.db import migrations, models


TABLE = "netbox_proxbox_proxboxpluginsettings"


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0044_overwrite_vm_cloudinit"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql=(
                        f'ALTER TABLE "{TABLE}" '
                        'ADD COLUMN IF NOT EXISTS "branching_enabled" boolean '
                        "NOT NULL DEFAULT FALSE;"
                        f' ALTER TABLE "{TABLE}" '
                        'ADD COLUMN IF NOT EXISTS "branch_name_prefix" varchar(64) '
                        "NOT NULL DEFAULT 'proxbox-sync';"
                        f' ALTER TABLE "{TABLE}" '
                        'ADD COLUMN IF NOT EXISTS "branch_on_conflict" varchar(16) '
                        "NOT NULL DEFAULT 'fail';"
                        f' ALTER TABLE "{TABLE}" '
                        'ADD COLUMN IF NOT EXISTS "netbox_to_proxmox_enabled" boolean '
                        "NOT NULL DEFAULT FALSE;"
                        f' ALTER TABLE "{TABLE}" '
                        'ADD COLUMN IF NOT EXISTS "netbox_to_proxmox_typed_confirmation" '
                        "varchar(64) NOT NULL DEFAULT '';"
                        f' ALTER TABLE "{TABLE}" '
                        'ADD COLUMN IF NOT EXISTS "apply_destroy_confirmed" boolean '
                        "NOT NULL DEFAULT FALSE;"
                    ),
                    reverse_sql=(
                        f'ALTER TABLE "{TABLE}" DROP COLUMN IF EXISTS "branching_enabled";'
                        f' ALTER TABLE "{TABLE}" DROP COLUMN IF EXISTS "branch_name_prefix";'
                        f' ALTER TABLE "{TABLE}" DROP COLUMN IF EXISTS "branch_on_conflict";'
                        f' ALTER TABLE "{TABLE}" '
                        'DROP COLUMN IF EXISTS "netbox_to_proxmox_enabled";'
                        f' ALTER TABLE "{TABLE}" '
                        'DROP COLUMN IF EXISTS "netbox_to_proxmox_typed_confirmation";'
                        f' ALTER TABLE "{TABLE}" '
                        'DROP COLUMN IF EXISTS "apply_destroy_confirmed";'
                    ),
                ),
            ],
            state_operations=[
                migrations.AddField(
                    model_name="proxboxpluginsettings",
                    name="branching_enabled",
                    field=models.BooleanField(
                        default=False,
                        verbose_name="Branching-enabled sync (Proxmox → NetBox)",
                        help_text=(
                            "When enabled, every Proxbox sync job creates a fresh "
                            "netbox-branching branch, runs the sync on that branch, "
                            "and merges it back into main on success. Requires the "
                            "netbox_branching plugin to be installed and listed last "
                            "in PLUGINS."
                        ),
                    ),
                ),
                migrations.AddField(
                    model_name="proxboxpluginsettings",
                    name="branch_name_prefix",
                    field=models.CharField(
                        default="proxbox-sync",
                        max_length=64,
                        verbose_name="Branch name prefix",
                        help_text=(
                            "Prefix used when auto-creating a NetBox branch per sync "
                            "job (e.g. proxbox-sync-<job_id>-<timestamp>)."
                        ),
                    ),
                ),
                migrations.AddField(
                    model_name="proxboxpluginsettings",
                    name="branch_on_conflict",
                    field=models.CharField(
                        default="fail",
                        max_length=16,
                        choices=[
                            ("fail", "Fail (leave branch open for review)"),
                            ("acknowledge", "Acknowledge and merge anyway"),
                        ],
                        verbose_name="Branch merge conflict policy",
                        help_text=(
                            "What to do when the auto-created sync branch reports "
                            "merge conflicts. 'fail' leaves the branch open for "
                            "operator review and marks the job failed. 'acknowledge' "
                            "retries the merge with acknowledge_conflicts=True."
                        ),
                    ),
                ),
                migrations.AddField(
                    model_name="proxboxpluginsettings",
                    name="netbox_to_proxmox_enabled",
                    field=models.BooleanField(
                        default=False,
                        verbose_name="Enable NetBox → Proxmox intent direction",
                        help_text=(
                            "Master flag for the intent-direction integration: "
                            "merging a branch flagged apply_to_proxmox=True dispatches "
                            "CREATE/UPDATE writes to Proxmox via proxbox-api. DELETE "
                            "still requires the separate DeletionRequest "
                            "authorization chain. Off by default."
                        ),
                    ),
                ),
                migrations.AddField(
                    model_name="proxboxpluginsettings",
                    name="netbox_to_proxmox_typed_confirmation",
                    field=models.CharField(
                        blank=True,
                        default="",
                        max_length=64,
                        verbose_name="Typed confirmation phrase",
                        help_text=(
                            "Operators enabling NetBox → Proxmox writes must type the "
                            "exact phrase 'allow-edit-and-add-actions' into this "
                            "field. Toggling the master flag back to off clears this "
                            "phrase, forcing a re-confirmation on re-enable."
                        ),
                    ),
                ),
                migrations.AddField(
                    model_name="proxboxpluginsettings",
                    name="apply_destroy_confirmed",
                    field=models.BooleanField(
                        default=False,
                        verbose_name="Allow apply-destroy authorization workflow",
                        help_text=(
                            "Per-branch destroy master switch. Even when set, every "
                            "destroy still flows through a separate DeletionRequest "
                            "approved by a user holding "
                            "netbox_proxbox.authorize_deletion_request. Off by "
                            "default."
                        ),
                    ),
                ),
            ],
        ),
    ]
