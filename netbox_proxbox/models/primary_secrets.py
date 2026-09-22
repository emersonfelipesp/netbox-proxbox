"""Primary endpoint credential encryption helpers."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Callable

from cryptography.fernet import Fernet

from netbox_proxbox.utils import encryption as enc_helpers


_SKIP_ENCRYPTION: ContextVar[bool] = ContextVar(
    "proxbox_skip_primary_secret_encryption", default=False
)
_CAPTURE_PLAINTEXT: ContextVar[Callable[[str], None] | None] = ContextVar(
    "proxbox_capture_primary_secret_plaintext", default=None
)


@contextmanager
def skip_primary_secret_encryption(
    capture_plaintext: Callable[[str], None] | None = None,
) -> Iterator[None]:
    """Keep transient OpenBao FastAPI candidates out of Fernet storage."""
    skip_token = _SKIP_ENCRYPTION.set(True)
    capture_token = _CAPTURE_PLAINTEXT.set(capture_plaintext)
    try:
        yield
    finally:
        _CAPTURE_PLAINTEXT.reset(capture_token)
        _SKIP_ENCRYPTION.reset(skip_token)


def primary_secret_encryption_is_skipped() -> bool:
    """Return whether an OpenBao owner transition bypasses Fernet handling."""
    return _SKIP_ENCRYPTION.get()


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
    if _SKIP_ENCRYPTION.get():
        value = "" if plaintext is None else str(plaintext)
        capture = _CAPTURE_PLAINTEXT.get()
        if value and capture is not None:
            capture(value)
        return ""
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
