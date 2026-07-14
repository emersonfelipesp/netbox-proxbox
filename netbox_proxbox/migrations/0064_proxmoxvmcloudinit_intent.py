"""Add create-time cloud-init intent fields to ProxmoxVMCloudInit.

These fields capture the cloud-init request the NMS stack sent at VM-create
time (hostname, network, DNS, agent, encrypted SSH public keys) plus a soft
integer reference to the netbox-nms ``CloudVMCredential`` PK. They are additive
and idempotent (see ``_idempotent_ops``) so the migration is safe against
clean, partial-legacy, and fully-applied databases.
"""

from __future__ import annotations

from django.db import migrations, models

from netbox_proxbox.migrations._idempotent_ops import add_field_idempotent

MODEL = "proxmoxvmcloudinit"


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0063_merge_rpc_enabled_service_monitoring"),
    ]

    operations = [
        add_field_idempotent(
            model_name=MODEL,
            field_name="is_intent",
            field=models.BooleanField(default=False),
        ),
        add_field_idempotent(
            model_name=MODEL,
            field_name="hostname",
            field=models.CharField(blank=True, max_length=255),
        ),
        add_field_idempotent(
            model_name=MODEL,
            field_name="search_domain",
            field=models.CharField(blank=True, max_length=255),
        ),
        add_field_idempotent(
            model_name=MODEL,
            field_name="dns_servers",
            field=models.CharField(blank=True, max_length=255),
        ),
        add_field_idempotent(
            model_name=MODEL,
            field_name="bridge",
            field=models.CharField(blank=True, max_length=64),
        ),
        add_field_idempotent(
            model_name=MODEL,
            field_name="vlan_tag",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        add_field_idempotent(
            model_name=MODEL,
            field_name="gateway",
            field=models.CharField(blank=True, max_length=64),
        ),
        add_field_idempotent(
            model_name=MODEL,
            field_name="ip_cidr",
            field=models.CharField(blank=True, max_length=64),
        ),
        add_field_idempotent(
            model_name=MODEL,
            field_name="ssh_pwauth",
            field=models.BooleanField(blank=True, null=True),
        ),
        add_field_idempotent(
            model_name=MODEL,
            field_name="enable_agent",
            field=models.BooleanField(blank=True, null=True),
        ),
        add_field_idempotent(
            model_name=MODEL,
            field_name="nms_credential_id",
            field=models.PositiveIntegerField(blank=True, db_index=True, null=True),
        ),
        add_field_idempotent(
            model_name=MODEL,
            field_name="sshkeys_enc",
            field=models.TextField(blank=True),
        ),
    ]
