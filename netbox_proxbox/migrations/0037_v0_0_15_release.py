"""Consolidated v0.0.15 release migration.

Folds every migration that previously lived between
``0036_add_overwrite_vm_type`` and the v0.0.15 release tip (across both
the v0.0.15 and develop branches) into a single forward-only delta.

This migration is the only file on disk between ``0036_add_overwrite_vm_type``
and ``0038_v0_0_16_release``. There is intentionally no ``replaces = [...]``
attribute: Django's squash auto-apply path requires *every* replaced
migration to be present in ``django_migrations``, which fails for the
realistic pre-v0.0.15 → v0.0.15 upgrade where the legacy lineage only ever
applied a subset of the 20-name fork before the squash was authored. The
``replaces`` reconciliation also forces graph rewrites that error out
(``multiple leaf nodes``) when partial state is detected. Treating this as
a plain forward migration sidesteps both problems.

Safety comes from idempotent schema ops. Every ``AddField`` and
``CreateModel`` is wrapped via the helpers in ``_idempotent_ops``.
``database_operations`` introspect the live schema and only invoke the
actual schema change when the column or table is missing;
``state_operations`` keep the original ``AddField`` / ``CreateModel``
verbatim so Django's project state, serializer parity, and
``makemigrations --check`` output match the non-idempotent original. This
protects reporter-style installs that applied the legacy lineage only
partially.

The five RunPython data callables below are carried over verbatim from
the original per-migration sources so existing rollouts upgrading from
0036 land on the same state as the original chain:

  * _backfill_use_https        (was 0038_fastapiendpoint_use_https)
  * _create_run_proxmox_action_perm (was 0041_run_proxmox_action_permission)
  * seed_default_vm_roles      (was develop 0045_seed_default_vm_roles)
  * register_last_synced_role_cf  (was develop 0046_register_last_synced_role_cf)
  * register_hardware_discovery_cfs (was develop 0049_register_hardware_discovery_cfs)
"""

import django.db.models.deletion
import netbox.models.deletion
import taggit.managers
import utilities.json
from django.db import migrations, models

from netbox_proxbox.migrations._idempotent_ops import (
    add_field_idempotent,
    create_model_idempotent,
)
from netbox_proxbox.migrations._v0_0_15_release_data import (
    _backfill_use_https,
    _create_run_proxmox_action_perm,
    _delete_run_proxmox_action_perm,
    _reverse_backfill_use_https,
    register_hardware_discovery_cfs,
    register_last_synced_role_cf,
    seed_default_vm_roles,
    unregister_hardware_discovery_cfs,
    unregister_last_synced_role_cf,
)


class Migration(migrations.Migration):

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
        ('contenttypes', '0002_remove_content_type_name'),
        ('core', '0018_concrete_objecttype'),
        ('dcim', '0227_alter_interface_speed_bigint'),
        ('extras', '0134_owner'),
        ('netbox_proxbox', '0036_add_overwrite_vm_type'),
        ('virtualization', '0052_gfk_indexes'),
    ]

    operations = [
        add_field_idempotent(
            model_name='fastapiendpoint',
            field_name='use_https',
            field=models.BooleanField(default=False),
        ),
        add_field_idempotent(
            model_name='proxboxpluginsettings',
            field_name='apply_destroy_confirmed',
            field=models.BooleanField(default=False),
        ),
        add_field_idempotent(
            model_name='proxboxpluginsettings',
            field_name='backup_batch_delay_ms',
            field=models.PositiveIntegerField(default=200),
        ),
        add_field_idempotent(
            model_name='proxboxpluginsettings',
            field_name='backup_batch_size',
            field=models.PositiveSmallIntegerField(default=5),
        ),
        add_field_idempotent(
            model_name='proxboxpluginsettings',
            field_name='branch_name_prefix',
            field=models.CharField(default='proxbox-sync', max_length=64),
        ),
        add_field_idempotent(
            model_name='proxboxpluginsettings',
            field_name='branch_on_conflict',
            field=models.CharField(default='fail', max_length=16),
        ),
        add_field_idempotent(
            model_name='proxboxpluginsettings',
            field_name='branching_enabled',
            field=models.BooleanField(default=False),
        ),
        add_field_idempotent(
            model_name='proxboxpluginsettings',
            field_name='debug_cache',
            field=models.BooleanField(default=False),
        ),
        add_field_idempotent(
            model_name='proxboxpluginsettings',
            field_name='default_role_lxc',
            field=models.ForeignKey(blank=True, limit_choices_to={'vm_role': True}, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='dcim.devicerole'),
        ),
        add_field_idempotent(
            model_name='proxboxpluginsettings',
            field_name='default_role_qemu',
            field=models.ForeignKey(blank=True, limit_choices_to={'vm_role': True}, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='dcim.devicerole'),
        ),
        add_field_idempotent(
            model_name='proxboxpluginsettings',
            field_name='delete_orphans',
            field=models.BooleanField(default=False),
        ),
        add_field_idempotent(
            model_name='proxboxpluginsettings',
            field_name='enable_tenant_name_regex',
            field=models.BooleanField(default=False),
        ),
        add_field_idempotent(
            model_name='proxboxpluginsettings',
            field_name='ensure_netbox_objects',
            field=models.BooleanField(default=True),
        ),
        add_field_idempotent(
            model_name='proxboxpluginsettings',
            field_name='expose_internal_errors',
            field=models.BooleanField(default=False),
        ),
        add_field_idempotent(
            model_name='proxboxpluginsettings',
            field_name='hardware_discovery_enabled',
            field=models.BooleanField(default=False),
        ),
        add_field_idempotent(
            model_name='proxboxpluginsettings',
            field_name='netbox_get_cache_max_bytes',
            field=models.PositiveBigIntegerField(default=52428800),
        ),
        add_field_idempotent(
            model_name='proxboxpluginsettings',
            field_name='netbox_get_cache_max_entries',
            field=models.PositiveIntegerField(default=4096),
        ),
        add_field_idempotent(
            model_name='proxboxpluginsettings',
            field_name='netbox_timeout',
            field=models.PositiveIntegerField(default=120),
        ),
        add_field_idempotent(
            model_name='proxboxpluginsettings',
            field_name='netbox_to_proxmox_enabled',
            field=models.BooleanField(default=False),
        ),
        add_field_idempotent(
            model_name='proxboxpluginsettings',
            field_name='netbox_to_proxmox_typed_confirmation',
            field=models.CharField(blank=True, default='', max_length=64),
        ),
        add_field_idempotent(
            model_name='proxboxpluginsettings',
            field_name='netbox_write_concurrency',
            field=models.PositiveSmallIntegerField(default=8),
        ),
        add_field_idempotent(
            model_name='proxboxpluginsettings',
            field_name='overwrite_ip_address_dns_name',
            field=models.BooleanField(default=True),
        ),
        add_field_idempotent(
            model_name='proxboxpluginsettings',
            field_name='overwrite_vm_cloudinit',
            field=models.BooleanField(default=True),
        ),
        add_field_idempotent(
            model_name='proxboxpluginsettings',
            field_name='parse_description_metadata',
            field=models.BooleanField(default=False),
        ),
        add_field_idempotent(
            model_name='proxboxpluginsettings',
            field_name='proxmox_fetch_concurrency',
            field=models.PositiveSmallIntegerField(default=8),
        ),
        add_field_idempotent(
            model_name='proxboxpluginsettings',
            field_name='tenant_name_regex_rules',
            field=models.JSONField(blank=True, default=list),
        ),
        add_field_idempotent(
            model_name='proxmoxendpoint',
            field_name='allow_writes',
            field=models.BooleanField(default=False),
        ),
        add_field_idempotent(
            model_name='proxmoxendpoint',
            field_name='default_role_lxc',
            field=models.ForeignKey(blank=True, limit_choices_to={'vm_role': True}, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='dcim.devicerole'),
        ),
        add_field_idempotent(
            model_name='proxmoxendpoint',
            field_name='default_role_qemu',
            field=models.ForeignKey(blank=True, limit_choices_to={'vm_role': True}, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='dcim.devicerole'),
        ),
        add_field_idempotent(
            model_name='proxmoxendpoint',
            field_name='enable_tenant_name_regex',
            field=models.BooleanField(blank=True, null=True),
        ),
        add_field_idempotent(
            model_name='proxmoxendpoint',
            field_name='overwrite_ip_address_dns_name',
            field=models.BooleanField(blank=True, null=True),
        ),
        add_field_idempotent(
            model_name='proxmoxendpoint',
            field_name='overwrite_vm_cloudinit',
            field=models.BooleanField(blank=True, null=True),
        ),
        add_field_idempotent(
            model_name='proxmoxendpoint',
            field_name='tenant_name_regex_rules',
            field=models.JSONField(blank=True, default=None, null=True),
        ),
        add_field_idempotent(
            model_name='proxmoxnode',
            field_name='default_role_lxc',
            field=models.ForeignKey(blank=True, limit_choices_to={'vm_role': True}, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='dcim.devicerole'),
        ),
        add_field_idempotent(
            model_name='proxmoxnode',
            field_name='default_role_qemu',
            field=models.ForeignKey(blank=True, limit_choices_to={'vm_role': True}, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='dcim.devicerole'),
        ),
        create_model_idempotent(
            name='NodeSSHCredential',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('created', models.DateTimeField(auto_now_add=True, null=True)),
                ('last_updated', models.DateTimeField(auto_now=True, null=True)),
                ('custom_field_data', models.JSONField(blank=True, default=dict, encoder=utilities.json.CustomFieldJSONEncoder)),
                ('username', models.CharField(max_length=64)),
                ('port', models.PositiveIntegerField(default=22)),
                ('auth_method', models.CharField(default='key', max_length=8)),
                ('known_host_fingerprint', models.CharField(max_length=128)),
                ('sudo_required', models.BooleanField(default=True)),
                ('password_enc', models.TextField(blank=True, default='')),
                ('private_key_enc', models.TextField(blank=True, default='')),
                ('node', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='ssh_credential', to='netbox_proxbox.proxmoxnode')),
                ('tags', taggit.managers.TaggableManager(through='extras.TaggedItem', to='extras.Tag')),
            ],
            options={
                'verbose_name': 'Node SSH credential',
                'verbose_name_plural': 'Node SSH credentials',
                'ordering': ('node',),
            },
            bases=(netbox.models.deletion.DeleteMixin, models.Model),
        ),
        create_model_idempotent(
            name='ProxmoxVMCloudInit',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('created', models.DateTimeField(auto_now_add=True, null=True)),
                ('last_updated', models.DateTimeField(auto_now=True, null=True)),
                ('custom_field_data', models.JSONField(blank=True, default=dict, encoder=utilities.json.CustomFieldJSONEncoder)),
                ('ciuser', models.CharField(blank=True, max_length=64)),
                ('sshkeys', models.TextField(blank=True)),
                ('ipconfig0', models.CharField(blank=True, max_length=255)),
                ('sshkeys_truncated', models.BooleanField(default=False)),
                ('last_synced', models.DateTimeField(auto_now=True)),
                ('tags', taggit.managers.TaggableManager(through='extras.TaggedItem', to='extras.Tag')),
                ('virtual_machine', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='proxmox_cloudinit', to='virtualization.virtualmachine')),
            ],
            options={
                'verbose_name': 'Proxmox VM cloud-init',
                'verbose_name_plural': 'Proxmox VM cloud-init records',
                'ordering': ('virtual_machine',),
            },
            bases=(netbox.models.deletion.DeleteMixin, models.Model),
        ),
        migrations.RunPython(
            _backfill_use_https,
            reverse_code=_reverse_backfill_use_https,
        ),
        migrations.RunPython(
            _create_run_proxmox_action_perm,
            reverse_code=_delete_run_proxmox_action_perm,
        ),
        migrations.RunPython(
            seed_default_vm_roles,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.RunPython(
            register_last_synced_role_cf,
            reverse_code=unregister_last_synced_role_cf,
        ),
        migrations.RunPython(
            register_hardware_discovery_cfs,
            reverse_code=unregister_hardware_discovery_cfs,
        ),
    ]
