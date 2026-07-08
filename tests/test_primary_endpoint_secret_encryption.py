"""Source contracts for primary endpoint credential encryption."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_primary_secret_models_use_encrypted_backing_fields() -> None:
    proxmox = _read("netbox_proxbox/models/proxmox_endpoint.py")
    fastapi = _read("netbox_proxbox/models/fastapi_endpoint.py")
    pbs = _read("netbox_proxbox/models/pbs_endpoint.py")
    pdm = _read("netbox_proxbox/models/pdm_endpoint.py")

    assert "password_enc = models.TextField" in proxmox
    assert "token_value_enc = models.TextField" in proxmox
    assert "def password(self) -> str" in proxmox
    assert "def token_value(self) -> str" in proxmox
    assert "password = models.CharField" not in proxmox
    assert "token_value = models.CharField" not in proxmox

    assert "token_enc = models.TextField" in fastapi
    assert "def token(self) -> str" in fastapi
    assert "token = models.CharField" not in fastapi

    for src in (pbs, pdm):
        assert "token_secret_enc = models.TextField" in src
        assert "def token_secret(self) -> str" in src
        assert "token_secret = models.CharField" not in src


def test_primary_secret_migration_encrypts_and_removes_plaintext_fields() -> None:
    migration = _read(
        "netbox_proxbox/migrations/0058_encrypt_primary_endpoint_secrets.py"
    )
    assert (
        "from netbox_proxbox.migrations._idempotent_ops import add_field_idempotent"
        in migration
    )
    assert "Fernet.generate_key()" in migration
    assert "encrypt_existing_primary_endpoint_secrets" in migration
    assert "def _table_columns(schema_editor, table: str) -> set[str]:" in migration
    assert "if source_column in columns and target_column in columns:" in migration
    assert "model.objects.only(*query_fields).iterator()" in migration
    for field in (
        'field_name="password"',
        'field_name="token_value"',
        'field_name="token"',
        'field_name="token_secret"',
    ):
        assert field in migration
    for field in (
        'field_name="password_enc"',
        'field_name="token_value_enc"',
        'field_name="token_enc"',
        'field_name="token_secret_enc"',
    ):
        assert field in migration
    assert migration.count("        add_field_idempotent(") == 5
    assert migration.count("        remove_field_idempotent(") == 5


def test_fastapi_endpoint_form_preserves_blank_token_submissions() -> None:
    form = _read("netbox_proxbox/forms/fastapi.py")
    assert 'render_value=False, attrs={"autocomplete": "new-password"}' in form
    assert 'submitted_token = (self.cleaned_data.get("token") or "").strip()' in form
    assert "if submitted_token:\n            instance.token = submitted_token" in form
