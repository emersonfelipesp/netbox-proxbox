"""Add nullable OpenBao references for node SSH credential material."""

from django.db import migrations, models

from ._idempotent_ops import add_field_idempotent


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0099_proxboxpluginsettings_openbao_policy_slug"),
    ]

    operations = [
        add_field_idempotent(
            "nodesshcredential",
            "openbao_password_credential_uuid",
            models.UUIDField(
                blank=True,
                editable=False,
                help_text="Opaque reference to the OpenBao SSH password credential.",
                null=True,
                verbose_name="OpenBao password credential UUID",
            ),
        ),
        add_field_idempotent(
            "nodesshcredential",
            "openbao_keypair_credential_uuid",
            models.UUIDField(
                blank=True,
                editable=False,
                help_text="Opaque reference to the OpenBao SSH key-pair credential.",
                null=True,
                verbose_name="OpenBao key-pair credential UUID",
            ),
        ),
    ]
