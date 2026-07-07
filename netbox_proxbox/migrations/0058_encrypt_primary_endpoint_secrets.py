"""Encrypt primary endpoint credentials at rest."""

import base64
import binascii

from cryptography.fernet import Fernet
from django.db import migrations, models


def _coerce_fernet_key(raw: str) -> bytes:
    encoded = raw.strip().encode("utf-8")
    try:
        Fernet(encoded)
    except (ValueError, TypeError, binascii.Error):
        if len(encoded) == 32:
            return base64.urlsafe_b64encode(encoded)
        raise
    return encoded


def _get_or_create_key(apps) -> bytes:
    Settings = apps.get_model("netbox_proxbox", "ProxboxPluginSettings")
    settings, _ = Settings.objects.get_or_create(singleton_key="default")
    key = (settings.encryption_key or "").strip()
    if not key:
        key = Fernet.generate_key().decode("ascii")
        settings.encryption_key = key
        settings.save(update_fields=["encryption_key"])
    return _coerce_fernet_key(key)


def _encrypt(value: object, *, fernet: Fernet) -> str:
    if value is None:
        return ""
    plaintext = str(value)
    if plaintext == "":
        return ""
    return fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")


def encrypt_existing_primary_endpoint_secrets(apps, schema_editor) -> None:
    """Move existing plaintext endpoint secrets into Fernet ciphertext columns."""
    fernet = Fernet(_get_or_create_key(apps))
    model_specs = (
        (
            "ProxmoxEndpoint",
            (("password", "password_enc"), ("token_value", "token_value_enc")),
        ),
        ("FastAPIEndpoint", (("token", "token_enc"),)),
        ("PBSEndpoint", (("token_secret", "token_secret_enc"),)),
        ("PDMEndpoint", (("token_secret", "token_secret_enc"),)),
    )

    for model_name, field_pairs in model_specs:
        model = apps.get_model("netbox_proxbox", model_name)
        update_fields = [target for _source, target in field_pairs]
        for obj in model.objects.all().iterator():
            changed = False
            for source, target in field_pairs:
                ciphertext = _encrypt(getattr(obj, source, None), fernet=fernet)
                if getattr(obj, target, "") != ciphertext:
                    setattr(obj, target, ciphertext)
                    changed = True
            if changed:
                obj.save(update_fields=update_fields)


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0057_proxboxpluginsettings_netbox_openapi_persist"),
        ("netbox_proxbox", "0057_sdn_bgp_sync_mode"),
    ]

    operations = [
        migrations.AddField(
            model_name="proxmoxendpoint",
            name="password_enc",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Fernet-encrypted Proxmox endpoint password ciphertext. Internal.",
                verbose_name="Encrypted password",
            ),
        ),
        migrations.AddField(
            model_name="proxmoxendpoint",
            name="token_value_enc",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Fernet-encrypted Proxmox API token value ciphertext. Internal.",
                verbose_name="Encrypted token value",
            ),
        ),
        migrations.AddField(
            model_name="fastapiendpoint",
            name="token_enc",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Fernet-encrypted backend token used by the ProxBox service. Internal.",
                verbose_name="Encrypted token",
            ),
        ),
        migrations.AddField(
            model_name="pbsendpoint",
            name="token_secret_enc",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Fernet-encrypted PBS API token secret ciphertext. Internal.",
                verbose_name="Encrypted token secret",
            ),
        ),
        migrations.AddField(
            model_name="pdmendpoint",
            name="token_secret_enc",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Fernet-encrypted PDM API token secret ciphertext. Internal.",
                verbose_name="Encrypted token secret",
            ),
        ),
        migrations.RunPython(
            encrypt_existing_primary_endpoint_secrets,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.RemoveField(
            model_name="proxmoxendpoint",
            name="password",
        ),
        migrations.RemoveField(
            model_name="proxmoxendpoint",
            name="token_value",
        ),
        migrations.RemoveField(
            model_name="fastapiendpoint",
            name="token",
        ),
        migrations.RemoveField(
            model_name="pbsendpoint",
            name="token_secret",
        ),
        migrations.RemoveField(
            model_name="pdmendpoint",
            name="token_secret",
        ),
    ]
