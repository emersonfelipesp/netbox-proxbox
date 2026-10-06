"""Reset the historical implicit OpenBao default when no references exist."""

from django.db import migrations


OPENBAO_REFERENCE_FIELDS = {
    "ProxmoxEndpoint": (
        "openbao_password_credential_uuid",
        "openbao_token_credential_uuid",
        "openbao_ssh_password_credential_uuid",
        "openbao_ssh_keypair_credential_uuid",
    ),
    "NodeSSHCredential": (
        "openbao_password_credential_uuid",
        "openbao_keypair_credential_uuid",
    ),
    "FastAPIEndpoint": ("openbao_token_credential_uuid",),
    "PBSEndpoint": ("openbao_token_credential_uuid",),
    "PDMEndpoint": ("openbao_token_credential_uuid",),
    "FirecrackerHost": ("openbao_agent_token_credential_uuid",),
    "ProxmoxVMCloudInit": (
        "openbao_password_credential_uuid",
        "openbao_keypair_credential_uuid",
    ),
}


def _has_openbao_references(apps, alias: str) -> bool:
    for model_name, field_names in OPENBAO_REFERENCE_FIELDS.items():
        model = apps.get_model("netbox_proxbox", model_name)
        for field_name in field_names:
            if (
                model.objects.using(alias)
                .filter(**{f"{field_name}__isnull": False})
                .exists()
            ):
                return True
    return False


def reset_implicit_openbao_storage_default(apps, schema_editor) -> None:
    """Restore Automatic only when no persisted OpenBao reference exists."""
    alias = schema_editor.connection.alias
    if _has_openbao_references(apps, alias):
        return
    settings_model = apps.get_model("netbox_proxbox", "ProxboxPluginSettings")
    settings_model.objects.using(alias).filter(
        credential_storage_backend="openbao"
    ).update(credential_storage_backend="")


class Migration(migrations.Migration):
    dependencies = [("netbox_proxbox", "0104_security_hardening")]

    operations = [
        migrations.RunPython(
            reset_implicit_openbao_storage_default,
            migrations.RunPython.noop,
        )
    ]
