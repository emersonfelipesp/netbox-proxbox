"""Primary endpoint credential encryption helpers."""

from __future__ import annotations

from cryptography.fernet import Fernet

from netbox_proxbox.utils import encryption as enc_helpers


def _get_or_create_primary_secret_key() -> str:
    """Return the plugin Fernet key, creating one for primary secrets if needed."""
    from netbox_proxbox.models.plugin_settings import ProxboxPluginSettings

    settings = ProxboxPluginSettings.get_solo()
    key = (settings.encryption_key or "").strip()
    if key:
        return key

    key = Fernet.generate_key().decode("ascii")
    settings.encryption_key = key
    settings.save(update_fields=["encryption_key"])
    return key


def _get_primary_secret_key() -> str:
    """Return the configured plugin Fernet key without mutating settings."""
    from netbox_proxbox.models.plugin_settings import ProxboxPluginSettings

    return (ProxboxPluginSettings.get_solo().encryption_key or "").strip()


def encrypt_primary_secret(plaintext: object | None) -> str:
    """Encrypt a primary endpoint secret, returning blank for empty input."""
    if plaintext is None:
        return ""
    value = str(plaintext)
    if value == "":
        return ""
    return enc_helpers.encrypt(value, key=_get_or_create_primary_secret_key())


def decrypt_primary_secret(ciphertext: str) -> str:
    """Decrypt a stored primary endpoint secret, returning blank for empty input."""
    if not ciphertext:
        return ""
    return enc_helpers.decrypt(ciphertext, key=_get_primary_secret_key())
