"""Consolidated v0.0.16 release migration.

Squashes all migrations added between ``0037_v0_0_15_release`` and the
v0.0.16 release tip (0038–0047, including both 0044 forks) into a single
forward-only delta.

Two layers of safety make this migration production-safe for every upgrade
path:

* **Layer A — ``replaces = [...]``** lists every migration this squash
  consumes. Django marks the squash as applied without re-running operations
  when *all* original migrations are already in ``django_migrations``.
* **Layer B — idempotent schema ops.** Every ``AddField`` and ``CreateModel``
  is wrapped via the helpers in ``_idempotent_ops``. ``database_operations``
  introspect the live schema and only invoke the actual schema change when the
  column or table is missing; ``state_operations`` keep the original
  ``AddField`` / ``CreateModel`` verbatim so Django's project state, serializer
  parity, and ``makemigrations --check`` output match the non-idempotent
  original.  The two ``SeparateDatabaseAndState`` operations from
  ``0044_overwrite_vm_proxmox_tags`` use ``RunSQL … IF NOT EXISTS`` directly
  and are carried over verbatim.

The RunPython data callable is carried over verbatim from the original
per-migration source:

  * register_intent_custom_fields  (was 0039_intent_custom_fields)

The ``0047_legacy_lineage_schema_repair`` RunPython is omitted: every table
and column it would create is already covered by the idempotent schema
operations above, and the ``replaces`` list ensures databases that applied
0047 individually will not re-run any operations.
"""

from __future__ import annotations

import uuid

import django.core.validators
import django.db.models.deletion
import netbox.models.deletion
import taggit.managers
import utilities.json
from django.conf import settings
from django.db import migrations, models

from netbox_proxbox.migrations._idempotent_ops import (
    add_field_idempotent,
    create_model_idempotent,
)
from netbox_proxbox.migrations._v0_0_16_release_data import (
    register_intent_custom_fields,
    unregister_intent_custom_fields,
)


class Migration(migrations.Migration):

    replaces = [
        ('netbox_proxbox', '0038_intent_permissions'),
        ('netbox_proxbox', '0039_intent_custom_fields'),
        ('netbox_proxbox', '0040_apply_job_full'),
        ('netbox_proxbox', '0041_deletion_request_full'),
        ('netbox_proxbox', '0042_pluginsettings_self_approve'),
        ('netbox_proxbox', '0043_pluginsettings_warn_plaintext'),
        ('netbox_proxbox', '0044_cloud_image_template'),
        ('netbox_proxbox', '0044_overwrite_vm_proxmox_tags'),
        ('netbox_proxbox', '0045_proxmoxendpoint_environment'),
        ('netbox_proxbox', '0046_pluginsettings_embed_description_metadata'),
        ('netbox_proxbox', '0047_legacy_lineage_schema_repair'),
    ]

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
        ('contenttypes', '0002_remove_content_type_name'),
        ('extras', '0134_owner'),
        ('netbox_proxbox', '0037_v0_0_15_release'),
        ('tenancy', '0023_add_mptt_tree_indexes'),
        ('virtualization', '0052_gfk_indexes'),
    ]

    operations = [
        # ── 0038_intent_permissions ──────────────────────────────────────────
        # Create ProxmoxApplyJob and DeletionRequest shell models (base fields
        # only; remaining columns are added by the AddField ops below).
        create_model_idempotent(
            name='ProxmoxApplyJob',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('created', models.DateTimeField(auto_now_add=True, null=True)),
                ('last_updated', models.DateTimeField(auto_now=True, null=True)),
                ('custom_field_data', models.JSONField(blank=True, default=dict, encoder=utilities.json.CustomFieldJSONEncoder)),
                ('name', models.CharField(blank=True, max_length=255)),
                ('tags', taggit.managers.TaggableManager(through='extras.TaggedItem', to='extras.Tag')),
            ],
            options={
                'verbose_name': 'Proxmox Apply Job',
                'verbose_name_plural': 'Proxmox Apply Jobs',
                'ordering': ('-pk',),
                'permissions': (
                    ('intent_create_vm', 'Can request CREATE of a Proxmox QEMU VM via intent'),
                    ('intent_update_vm', 'Can request UPDATE of a Proxmox QEMU VM via intent'),
                    ('intent_delete_vm', 'Can request DELETE of a Proxmox QEMU VM via intent'),
                    ('intent_create_lxc', 'Can request CREATE of a Proxmox LXC container via intent'),
                    ('intent_update_lxc', 'Can request UPDATE of a Proxmox LXC container via intent'),
                    ('intent_delete_lxc', 'Can request DELETE of a Proxmox LXC container via intent'),
                ),
            },
            bases=(netbox.models.deletion.DeleteMixin, models.Model),
        ),
        create_model_idempotent(
            name='DeletionRequest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('created', models.DateTimeField(auto_now_add=True, null=True)),
                ('last_updated', models.DateTimeField(auto_now=True, null=True)),
                ('custom_field_data', models.JSONField(blank=True, default=dict, encoder=utilities.json.CustomFieldJSONEncoder)),
                ('name', models.CharField(blank=True, max_length=255)),
                ('tags', taggit.managers.TaggableManager(through='extras.TaggedItem', to='extras.Tag')),
            ],
            options={
                'verbose_name': 'Deletion Request',
                'verbose_name_plural': 'Deletion Requests',
                'ordering': ('-pk',),
                'permissions': (
                    (
                        'authorize_deletion_request',
                        'Can authorize (approve/reject) a Proxmox DeletionRequest',
                    ),
                ),
            },
            bases=(netbox.models.deletion.DeleteMixin, models.Model),
        ),
        # ── 0039_intent_custom_fields ────────────────────────────────────────
        migrations.RunPython(
            register_intent_custom_fields,
            reverse_code=unregister_intent_custom_fields,
        ),
        # ── 0040_apply_job_full ──────────────────────────────────────────────
        add_field_idempotent(
            model_name='proxmoxapplyjob',
            field_name='branch_id',
            field=models.IntegerField(
                blank=True,
                help_text=(
                    'Primary key of the merged netbox-branching Branch that '
                    'triggered this run.'
                ),
                null=True,
                verbose_name='Branch ID',
            ),
        ),
        add_field_idempotent(
            model_name='proxmoxapplyjob',
            field_name='branch_name',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Name of the merged netbox-branching Branch at queue time.',
                max_length=255,
                verbose_name='Branch name',
            ),
        ),
        add_field_idempotent(
            model_name='proxmoxapplyjob',
            field_name='user',
            field=models.ForeignKey(
                blank=True,
                help_text='User associated with the branch merge that queued this run.',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='+',
                to=settings.AUTH_USER_MODEL,
                verbose_name='User',
            ),
        ),
        add_field_idempotent(
            model_name='proxmoxapplyjob',
            field_name='run_uuid',
            field=models.UUIDField(
                default=uuid.uuid4,
                editable=False,
                help_text='Stable run identifier shared with proxbox-api apply logs.',
                unique=True,
                verbose_name='Run UUID',
            ),
        ),
        add_field_idempotent(
            model_name='proxmoxapplyjob',
            field_name='state',
            field=models.CharField(
                choices=[
                    ('queued', 'Queued'),
                    ('running', 'Running'),
                    ('succeeded', 'Succeeded'),
                    ('failed', 'Failed'),
                    ('partial', 'Partial'),
                ],
                default='queued',
                help_text='Current dry-run executor state.',
                max_length=32,
                verbose_name='State',
            ),
        ),
        add_field_idempotent(
            model_name='proxmoxapplyjob',
            field_name='per_vm_results',
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text='Dry-run result stubs keyed by VM identifier.',
                verbose_name='Per-VM results',
            ),
        ),
        add_field_idempotent(
            model_name='proxmoxapplyjob',
            field_name='started_at',
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name='Started at',
            ),
        ),
        add_field_idempotent(
            model_name='proxmoxapplyjob',
            field_name='finished_at',
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name='Finished at',
            ),
        ),
        # ── 0041_deletion_request_full ───────────────────────────────────────
        add_field_idempotent(
            model_name='deletionrequest',
            field_name='branch_id',
            field=models.IntegerField(blank=True, null=True),
        ),
        add_field_idempotent(
            model_name='deletionrequest',
            field_name='branch_name',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        add_field_idempotent(
            model_name='deletionrequest',
            field_name='requested_by',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='proxbox_deletion_requests_requested',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        add_field_idempotent(
            model_name='deletionrequest',
            field_name='authorizer',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='proxbox_deletion_requests_authorized',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        add_field_idempotent(
            model_name='deletionrequest',
            field_name='state',
            field=models.CharField(
                choices=[
                    ('pending', 'Pending'),
                    ('approved', 'Approved'),
                    ('rejected', 'Rejected'),
                    ('executing', 'Executing'),
                    ('succeeded', 'Succeeded'),
                    ('failed', 'Failed'),
                ],
                default='pending',
                max_length=16,
            ),
        ),
        add_field_idempotent(
            model_name='deletionrequest',
            field_name='vmid',
            field=models.IntegerField(blank=True, null=True),
        ),
        add_field_idempotent(
            model_name='deletionrequest',
            field_name='node',
            field=models.CharField(blank=True, default='', max_length=64),
        ),
        add_field_idempotent(
            model_name='deletionrequest',
            field_name='kind',
            field=models.CharField(
                choices=[('qemu', 'qemu'), ('lxc', 'lxc')],
                default='qemu',
                max_length=8,
            ),
        ),
        add_field_idempotent(
            model_name='deletionrequest',
            field_name='metadata_snapshot',
            field=models.JSONField(blank=True, default=dict),
        ),
        add_field_idempotent(
            model_name='deletionrequest',
            field_name='reject_reason',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        add_field_idempotent(
            model_name='deletionrequest',
            field_name='executor_run_uuid',
            field=models.UUIDField(blank=True, null=True),
        ),
        add_field_idempotent(
            model_name='deletionrequest',
            field_name='requested_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        add_field_idempotent(
            model_name='deletionrequest',
            field_name='approved_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        add_field_idempotent(
            model_name='deletionrequest',
            field_name='executed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        # ── 0042_pluginsettings_self_approve ─────────────────────────────────
        add_field_idempotent(
            model_name='proxboxpluginsettings',
            field_name='intent_apply_authorization_self_approve_allowed',
            field=models.BooleanField(
                default=False,
                help_text=(
                    'When enabled, the user who requested a Proxmox deletion may also approve '
                    'the DeletionRequest. Leave disabled for four-eyes authorization.'
                ),
                verbose_name='Allow deletion request self-approval',
            ),
        ),
        add_field_idempotent(
            model_name='proxboxpluginsettings',
            field_name='intent_deletion_request_ttl_days',
            field=models.IntegerField(
                default=7,
                help_text=(
                    'Pending DeletionRequests older than this many days are auto-rejected '
                    'and the pending-deletion tag is removed from Proxmox best-effort.'
                ),
                validators=[django.core.validators.MinValueValidator(1)],
                verbose_name='Deletion request TTL (days)',
            ),
        ),
        # ── 0043_pluginsettings_warn_plaintext ───────────────────────────────
        add_field_idempotent(
            model_name='proxboxpluginsettings',
            field_name='intent_warn_plaintext_password',
            field=models.BooleanField(
                default=True,
                help_text=(
                    'When enabled, the intent merge validator emits a warning if '
                    'cloud_init_user_data contains a plaintext password line.'
                ),
                verbose_name='Warn on plaintext cloud-init passwords',
            ),
        ),
        # ── 0044_cloud_image_template ────────────────────────────────────────
        create_model_idempotent(
            name='CloudImageTemplate',
            fields=[
                (
                    'custom_field_data',
                    models.JSONField(
                        blank=True,
                        default=dict,
                        encoder=utilities.json.CustomFieldJSONEncoder,
                    ),
                ),
                ('created', models.DateTimeField(auto_now_add=True, null=True)),
                ('last_updated', models.DateTimeField(auto_now=True, null=True)),
                (
                    'id',
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    'name',
                    models.CharField(
                        help_text='Human-readable cloud image template name.',
                        max_length=255,
                        verbose_name='Name',
                    ),
                ),
                (
                    'slug',
                    models.SlugField(
                        help_text='Unique slug used by API clients and automation.',
                        max_length=255,
                        unique=True,
                        verbose_name='Slug',
                    ),
                ),
                (
                    'description',
                    models.TextField(
                        blank=True,
                        help_text='Optional operator-facing description for this cloud image.',
                        verbose_name='Description',
                    ),
                ),
                (
                    'source_vmid',
                    models.PositiveIntegerField(
                        help_text='Proxmox VMID of the source cloud-image template.',
                        verbose_name='Source VMID',
                    ),
                ),
                (
                    'os_family',
                    models.CharField(
                        choices=[
                            ('ubuntu', 'Ubuntu'),
                            ('debian', 'Debian'),
                            ('rocky', 'Rocky Linux'),
                            ('alpine', 'Alpine Linux'),
                            ('generic', 'Generic Linux'),
                        ],
                        default='generic',
                        help_text='Operating-system family represented by this image.',
                        max_length=32,
                        verbose_name='OS family',
                    ),
                ),
                (
                    'os_release',
                    models.CharField(
                        blank=True,
                        help_text='Optional OS release or codename, for example jammy.',
                        max_length=64,
                        verbose_name='OS release',
                    ),
                ),
                (
                    'default_ciuser',
                    models.CharField(
                        default='cloud-user',
                        help_text='Default ciuser value supplied when provisioning from this image.',
                        max_length=64,
                        verbose_name='Default cloud-init user',
                    ),
                ),
                (
                    'is_active',
                    models.BooleanField(
                        default=True,
                        help_text='Inactive templates are hidden from tenant provisioning flows.',
                        verbose_name='Active',
                    ),
                ),
                (
                    'allowed_tenants',
                    models.ManyToManyField(
                        blank=True,
                        help_text='Tenants allowed to use this image. Leave empty for all tenants.',
                        related_name='proxbox_cloud_image_templates',
                        to='tenancy.tenant',
                        verbose_name='Allowed tenants',
                    ),
                ),
                (
                    'cluster',
                    models.ForeignKey(
                        help_text='NetBox cluster that contains the Proxmox source template VMID.',
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='proxbox_cloud_image_templates',
                        to='virtualization.cluster',
                        verbose_name='Cluster',
                    ),
                ),
                (
                    'tags',
                    taggit.managers.TaggableManager(
                        through='extras.TaggedItem',
                        to='extras.Tag',
                    ),
                ),
            ],
            options={
                'verbose_name': 'Cloud image template',
                'verbose_name_plural': 'Cloud image templates',
                'ordering': ('cluster', 'name', 'source_vmid'),
                'permissions': [
                    (
                        'provision_cloud_vm',
                        'Can provision a VM from a cloud image template',
                    ),
                ],
                'unique_together': {('cluster', 'source_vmid')},
            },
        ),
        # ── 0044_overwrite_vm_proxmox_tags ───────────────────────────────────
        # Uses RunSQL ADD COLUMN IF NOT EXISTS directly (carried over verbatim).
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql=(
                        'ALTER TABLE "netbox_proxbox_proxboxpluginsettings" '
                        'ADD COLUMN IF NOT EXISTS "overwrite_vm_proxmox_tags" boolean NOT NULL DEFAULT TRUE;'
                    ),
                    reverse_sql=(
                        'ALTER TABLE "netbox_proxbox_proxboxpluginsettings" '
                        'DROP COLUMN IF EXISTS "overwrite_vm_proxmox_tags";'
                    ),
                ),
            ],
            state_operations=[
                migrations.AddField(
                    model_name='proxboxpluginsettings',
                    name='overwrite_vm_proxmox_tags',
                    field=models.BooleanField(
                        default=True,
                        verbose_name='Sync Proxmox tags',
                        help_text=(
                            'When enabled, Proxmox VM tags (the `;`-separated `tags` field on QEMU/LXC '
                            'config) are mirrored as NetBox tags on the synced VirtualMachine. Tag colors '
                            'match the Proxmox `tag-style` color-map when available, otherwise a stable '
                            'deterministic color is used. When disabled, Proxmox-sourced tags are never '
                            'created or attached.'
                        ),
                    ),
                ),
            ],
        ),
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql=(
                        'ALTER TABLE "netbox_proxbox_proxmoxendpoint" '
                        'ADD COLUMN IF NOT EXISTS "overwrite_vm_proxmox_tags" boolean NULL;'
                    ),
                    reverse_sql=(
                        'ALTER TABLE "netbox_proxbox_proxmoxendpoint" '
                        'DROP COLUMN IF EXISTS "overwrite_vm_proxmox_tags";'
                    ),
                ),
            ],
            state_operations=[
                migrations.AddField(
                    model_name='proxmoxendpoint',
                    name='overwrite_vm_proxmox_tags',
                    field=models.BooleanField(
                        blank=True,
                        null=True,
                        verbose_name='Sync Proxmox tags',
                        help_text='Per-endpoint override for the global Proxbox setting. Leave blank to inherit.',
                    ),
                ),
            ],
        ),
        # ── 0045_proxmoxendpoint_environment ─────────────────────────────────
        add_field_idempotent(
            model_name='proxmoxendpoint',
            field_name='environment',
            field=models.CharField(
                blank=True,
                choices=[
                    ('production', 'Production'),
                    ('staging', 'Staging'),
                    ('development', 'Development'),
                    ('homologation', 'Homologation'),
                    ('testing', 'Testing'),
                    ('lab', 'Lab'),
                ],
                help_text=(
                    'Operator-selected lifecycle stage (e.g. production, development, '
                    'homologation). Manual classification only; never written by sync.'
                ),
                max_length=32,
                null=True,
                verbose_name='Environment',
            ),
        ),
        # ── 0046_pluginsettings_embed_description_metadata ───────────────────
        add_field_idempotent(
            model_name='proxboxpluginsettings',
            field_name='embed_description_metadata',
            field=models.BooleanField(
                default=False,
                help_text=(
                    'When enabled, intent-direction create/update writes to Proxmox '
                    'append a fenced ``netbox-metadata`` JSON block of NetBox FK ids '
                    '(role, tenant, site, platform, cluster, device) to the Proxmox '
                    "object's description. Pairs with ``parse_description_metadata`` "
                    'to round-trip NetBox metadata through Proxmox without drift. '
                    'Disabled by default.'
                ),
                verbose_name='Embed description metadata',
            ),
        ),
        # ── 0047_legacy_lineage_schema_repair ────────────────────────────────
        # Omitted: every table and column it creates is already covered by the
        # idempotent ops above. Databases that applied 0047 individually are
        # handled by the replaces list.
    ]
