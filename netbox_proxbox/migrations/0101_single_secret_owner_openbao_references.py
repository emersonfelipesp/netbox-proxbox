"""Add OpenBao UUID references for single-secret credential owners."""

from django.db import migrations, models

from ._idempotent_ops import add_field_idempotent


class Migration(migrations.Migration):
    dependencies = [("netbox_proxbox", "0100_nodesshcredential_openbao_references")]

    operations = [
        add_field_idempotent(
            "fastapiendpoint",
            "openbao_token_credential_uuid",
            models.UUIDField(
                blank=True,
                editable=False,
                help_text="Opaque reference to the OpenBao backend API token.",
                null=True,
                verbose_name="OpenBao token credential UUID",
            ),
        ),
        add_field_idempotent(
            "pbsendpoint",
            "openbao_token_credential_uuid",
            models.UUIDField(
                blank=True,
                editable=False,
                help_text="Opaque reference to the OpenBao PBS API token.",
                null=True,
                verbose_name="OpenBao token credential UUID",
            ),
        ),
        add_field_idempotent(
            "pdmendpoint",
            "openbao_token_credential_uuid",
            models.UUIDField(
                blank=True,
                editable=False,
                help_text="Opaque reference to the OpenBao PDM API token.",
                null=True,
                verbose_name="OpenBao token credential UUID",
            ),
        ),
        add_field_idempotent(
            "firecrackerhost",
            "openbao_agent_token_credential_uuid",
            models.UUIDField(
                blank=True,
                editable=False,
                help_text="Opaque reference to the OpenBao Firecracker agent token.",
                null=True,
                verbose_name="OpenBao agent token credential UUID",
            ),
        ),
    ]
