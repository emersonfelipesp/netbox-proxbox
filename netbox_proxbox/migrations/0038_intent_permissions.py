"""Sub-PR B (#379): register the shell ProxmoxApplyJob / DeletionRequest models.

Creates the minimal table shapes required to attach the seven NetBox→Proxmox
intent RBAC permissions to real ContentTypes. The Meta.permissions tuple on
each model is Django's standard hook — running ``migrate`` calls
``create_permissions`` which inserts the seven rows in ``auth_permission``:

  * netbox_proxbox.intent_create_vm
  * netbox_proxbox.intent_update_vm
  * netbox_proxbox.intent_delete_vm
  * netbox_proxbox.intent_create_lxc
  * netbox_proxbox.intent_update_lxc
  * netbox_proxbox.intent_delete_lxc
  * netbox_proxbox.authorize_deletion_request

The first six attach to the ``proxmoxapplyjob`` ContentType (request-side).
The seventh attaches to the ``deletionrequest`` ContentType (authorize-side).
Four-eyes requires the request-side and authorize-side permissions to live on
distinct ContentTypes so they can be granted independently.

Both models are promoted to their full schemas in later sub-PRs:

  * Sub-PR E (0040_apply_job_full)        — ProxmoxApplyJob
  * Sub-PR H (0041_deletion_request_full) — DeletionRequest

Idempotent schema ops: every ``CreateModel`` is routed through
``create_model_idempotent`` so reporter-style installs that already created
these tables under the deleted legacy lineage do not abort with
``DuplicateTable``. See ``_idempotent_ops`` for the wrapper contract.
"""

from __future__ import annotations

import netbox.models.deletion
import taggit.managers
import utilities.json
from django.db import migrations, models

from netbox_proxbox.migrations._idempotent_ops import create_model_idempotent


class Migration(migrations.Migration):

    dependencies = [
        ('extras', '0134_owner'),
        ('netbox_proxbox', '0037_v0_0_15_release'),
    ]

    operations = [
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
    ]
