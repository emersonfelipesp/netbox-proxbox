"""Shared stand-ins for ``netbox_proxbox.choices`` in mocked loaders."""

from __future__ import annotations

from types import SimpleNamespace


def attach_credential_storage_backend_choices(choices_mod: object) -> object:
    """Ensure a stub choices module exposes ``CredentialStorageBackendChoices``."""
    if hasattr(choices_mod, "CredentialStorageBackendChoices"):
        return choices_mod
    choices_mod.CredentialStorageBackendChoices = SimpleNamespace(
        OPENBAO="openbao",
        LEGACY_ENCRYPTED="legacy_encrypted",
        CHOICES=(
            ("openbao", "OpenBao (default)"),
            ("legacy_encrypted", "Legacy Fernet-encrypted local storage"),
        ),
    )
    return choices_mod
