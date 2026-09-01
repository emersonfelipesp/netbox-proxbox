from django.db import migrations, models
from django.db.models import Q

from netbox_proxbox.choices import CredentialStorageBackendChoices
from netbox_proxbox.migrations._idempotent_ops import add_field_idempotent

LEGACY = CredentialStorageBackendChoices.LEGACY_ENCRYPTED


def _preserve_legacy_storage_for_existing_credentials(apps, schema_editor):
    """Keep Fernet-backed endpoints on the legacy path after upgrade."""
    ProxmoxEndpoint = apps.get_model("netbox_proxbox", "ProxmoxEndpoint")
    ProxboxPluginSettings = apps.get_model("netbox_proxbox", "ProxboxPluginSettings")

    legacy_filter = (
        Q(password_enc__gt="")
        | Q(token_value_enc__gt="")
        | Q(ssh_password_enc__gt="")
        | Q(ssh_private_key_enc__gt="")
    )
    if not ProxmoxEndpoint.objects.filter(legacy_filter).exists():
        return

    ProxboxPluginSettings.objects.update(credential_storage_backend=LEGACY)
    ProxmoxEndpoint.objects.filter(legacy_filter).update(
        credential_storage_backend=LEGACY
    )


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0082_proxmoxendpoint_allow_packer_template_builds"),
    ]

    operations = [
        add_field_idempotent(
            "proxboxpluginsettings",
            "credential_storage_backend",
            models.CharField(
                choices=CredentialStorageBackendChoices,
                default=CredentialStorageBackendChoices.OPENBAO,
                max_length=32,
                verbose_name="Credential storage backend",
            ),
        ),
        add_field_idempotent(
            "proxboxpluginsettings",
            "openbao_service_username",
            models.CharField(
                blank=True,
                default="",
                max_length=150,
                verbose_name="OpenBao service username",
            ),
        ),
        add_field_idempotent(
            "proxmoxendpoint",
            "credential_storage_backend",
            models.CharField(
                blank=True,
                choices=CredentialStorageBackendChoices,
                default="",
                max_length=32,
                verbose_name="Credential storage backend",
            ),
        ),
        add_field_idempotent(
            "proxmoxendpoint",
            "openbao_password_credential_uuid",
            models.UUIDField(blank=True, editable=False, null=True),
        ),
        add_field_idempotent(
            "proxmoxendpoint",
            "openbao_token_credential_uuid",
            models.UUIDField(blank=True, editable=False, null=True),
        ),
        add_field_idempotent(
            "proxmoxendpoint",
            "openbao_ssh_password_credential_uuid",
            models.UUIDField(blank=True, editable=False, null=True),
        ),
        add_field_idempotent(
            "proxmoxendpoint",
            "openbao_ssh_keypair_credential_uuid",
            models.UUIDField(blank=True, editable=False, null=True),
        ),
        migrations.RunPython(
            _preserve_legacy_storage_for_existing_credentials,
            migrations.RunPython.noop,
        ),
    ]
