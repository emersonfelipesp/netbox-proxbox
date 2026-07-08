"""Encrypt primary endpoint credentials at rest."""

import base64
import binascii

from cryptography.fernet import Fernet
from django.core.exceptions import FieldDoesNotExist
from django.db import migrations, models

from netbox_proxbox.migrations._idempotent_ops import add_field_idempotent


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


def _table_columns(schema_editor, table: str) -> set[str]:
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        return {
            description.name
            for description in connection.introspection.get_table_description(
                cursor, table
            )
        }


def _field_column(model, field_name: str) -> str | None:
    try:
        return model._meta.get_field(field_name).column
    except FieldDoesNotExist:
        return None


def _remove_field_if_present(model_name: str, field_name: str):
    def forwards(apps, schema_editor) -> None:
        model = apps.get_model("netbox_proxbox", model_name)
        try:
            field = model._meta.get_field(field_name)
        except FieldDoesNotExist:
            return
        columns = _table_columns(schema_editor, model._meta.db_table)
        if field.column not in columns:
            return
        schema_editor.remove_field(model, field)

    return forwards


def remove_field_idempotent(
    model_name: str,
    field_name: str,
) -> migrations.SeparateDatabaseAndState:
    return migrations.SeparateDatabaseAndState(
        database_operations=[
            migrations.RunPython(
                _remove_field_if_present(model_name, field_name),
                reverse_code=migrations.RunPython.noop,
            ),
        ],
        state_operations=[
            migrations.RemoveField(
                model_name=model_name,
                name=field_name,
            ),
        ],
    )


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
        columns = _table_columns(schema_editor, model._meta.db_table)
        present_pairs = []
        for source, target in field_pairs:
            source_column = _field_column(model, source)
            target_column = _field_column(model, target)
            if source_column in columns and target_column in columns:
                present_pairs.append((source, target))
        if not present_pairs:
            continue

        update_fields = [target for _source, target in present_pairs]
        query_fields = sorted({field for pair in present_pairs for field in pair})
        for obj in model.objects.only(*query_fields).iterator():
            changed = False
            for source, target in present_pairs:
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
        add_field_idempotent(
            model_name="proxmoxendpoint",
            field_name="password_enc",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Fernet-encrypted Proxmox endpoint password ciphertext. Internal.",
                verbose_name="Encrypted password",
            ),
        ),
        add_field_idempotent(
            model_name="proxmoxendpoint",
            field_name="token_value_enc",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Fernet-encrypted Proxmox API token value ciphertext. Internal.",
                verbose_name="Encrypted token value",
            ),
        ),
        add_field_idempotent(
            model_name="fastapiendpoint",
            field_name="token_enc",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Fernet-encrypted backend token used by the ProxBox service. Internal.",
                verbose_name="Encrypted token",
            ),
        ),
        add_field_idempotent(
            model_name="pbsendpoint",
            field_name="token_secret_enc",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Fernet-encrypted PBS API token secret ciphertext. Internal.",
                verbose_name="Encrypted token secret",
            ),
        ),
        add_field_idempotent(
            model_name="pdmendpoint",
            field_name="token_secret_enc",
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
        remove_field_idempotent(
            model_name="proxmoxendpoint",
            field_name="password",
        ),
        remove_field_idempotent(
            model_name="proxmoxendpoint",
            field_name="token_value",
        ),
        remove_field_idempotent(
            model_name="fastapiendpoint",
            field_name="token",
        ),
        remove_field_idempotent(
            model_name="pbsendpoint",
            field_name="token_secret",
        ),
        remove_field_idempotent(
            model_name="pdmendpoint",
            field_name="token_secret",
        ),
    ]
