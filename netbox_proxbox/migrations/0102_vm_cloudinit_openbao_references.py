"""Add OpenBao UUID references for VM cloud-init login credentials."""

from django.db import migrations, models

from ._idempotent_ops import add_field_idempotent


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0101_single_secret_owner_openbao_references"),
    ]

    operations = [
        add_field_idempotent(
            "proxmoxvmcloudinit",
            "openbao_password_credential_uuid",
            models.UUIDField(
                blank=True,
                editable=False,
                help_text="Opaque reference to the OpenBao VM login password.",
                null=True,
                verbose_name="OpenBao password credential UUID",
            ),
        ),
        add_field_idempotent(
            "proxmoxvmcloudinit",
            "openbao_keypair_credential_uuid",
            models.UUIDField(
                blank=True,
                editable=False,
                help_text="Opaque reference to the OpenBao VM login SSH keypair.",
                null=True,
                verbose_name="OpenBao keypair credential UUID",
            ),
        ),
    ]
