"""Fernet symmetric-encryption helpers for credentials at rest.

The key is read from `ProxboxPluginSettings.encryption_key` (singleton, see
`netbox_proxbox/models/plugin_settings.py`). When the setting is empty, every
encrypt/decrypt call raises `EncryptionKeyMissing` — the hardware-discovery
feature refuses to operate in that state.

The Fernet key format is a 32-byte url-safe base64 string. We accept either
form directly (already Fernet-shaped) or a raw 32-byte secret which we encode
on the fly. This matches what `proxbox-api` already does for its own
encryption flow.
"""

from __future__ import annotations

import base64
import binascii

from cryptography.fernet import Fernet, InvalidToken


class EncryptionError(Exception):
    """Base class for encryption helper failures."""


class EncryptionKeyMissing(EncryptionError):
    """Raised when ``ProxboxPluginSettings.encryption_key`` is empty."""


class EncryptionKeyInvalid(EncryptionError):
    """Raised when the configured key is not a usable Fernet key."""


class DecryptionFailed(EncryptionError):
    """Raised when ciphertext could not be decrypted with the current key."""


def _coerce_fernet_key(raw: str) -> bytes:
    """Return a 44-byte url-safe base64 Fernet key derived from ``raw``.

    Accepts the already-canonical Fernet key form (44 url-safe base64 chars)
    or a 32-byte raw secret that we url-safe base64 encode ourselves.
    """
    if not raw:
        raise EncryptionKeyMissing(
            "ProxboxPluginSettings.encryption_key is empty; refusing to "
            "encrypt or decrypt credentials."
        )
    encoded = raw.strip().encode("utf-8")
    try:
        Fernet(encoded)
    except (ValueError, TypeError, binascii.Error):
        if len(encoded) == 32:
            return base64.urlsafe_b64encode(encoded)
        raise EncryptionKeyInvalid(
            "ProxboxPluginSettings.encryption_key is not a valid Fernet key "
            "(must be a 32-byte secret or a 44-byte url-safe base64 string)."
        ) from None
    return encoded


def _fernet(key: str) -> Fernet:
    return Fernet(_coerce_fernet_key(key))


def encrypt(plaintext: str, *, key: str) -> str:
    """Encrypt ``plaintext`` and return a url-safe Fernet token (str)."""
    if plaintext == "":
        return ""
    token = _fernet(key).encrypt(plaintext.encode("utf-8"))
    return token.decode("ascii")


def decrypt(ciphertext: str, *, key: str) -> str:
    """Decrypt a Fernet token and return the plaintext string."""
    if ciphertext == "":
        return ""
    try:
        plaintext = _fernet(key).decrypt(ciphertext.encode("ascii"))
    except InvalidToken as exc:
        raise DecryptionFailed(
            "Stored credential could not be decrypted with the current "
            "ProxboxPluginSettings.encryption_key. The key may have been "
            "rotated since this row was saved."
        ) from exc
    return plaintext.decode("utf-8")
