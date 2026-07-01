"""Pure helpers for the Terminal-tab SSH credential modal.

These validate/normalize the credential object an operator types into the
Terminal-tab modal (store or one-shot). They are intentionally free of Django /
NetBox request state so they can be unit-tested without bootstrapping NetBox —
`views/endpoints/proxmox.py` imports them.
"""

from __future__ import annotations

from netbox_proxbox.models.ssh_credential import (
    AUTH_METHOD_KEY,
    AUTH_METHOD_PASSWORD,
)


def validate_terminal_credential(credential: object) -> tuple[dict | None, str | None]:
    """Validate a credential object typed into the Terminal-tab modal.

    Returns ``(normalized_dict, None)`` on success or ``(None, error)`` on
    failure. The normalized dict carries ``username``, ``port``, ``auth_method``,
    ``password``, ``private_key``, and ``known_host_fingerprint``. A pinned
    host-key fingerprint is mandatory for both the store and one-shot paths
    because proxbox-api refuses to connect without it.
    """
    if not isinstance(credential, dict):
        return None, "Credential payload must be an object."
    username = str(credential.get("username") or "").strip()
    if not username:
        return None, "SSH username is required."
    fingerprint = str(credential.get("known_host_fingerprint") or "").strip()
    if not fingerprint:
        return None, (
            'Host-key fingerprint is required. Use "Fetch host key" to obtain it.'
        )
    password = str(credential.get("password") or "")
    private_key = str(credential.get("private_key") or "")
    auth_method = str(credential.get("auth_method") or "").strip().lower()
    if auth_method not in (AUTH_METHOD_PASSWORD, AUTH_METHOD_KEY):
        auth_method = AUTH_METHOD_KEY if private_key.strip() else AUTH_METHOD_PASSWORD
    if auth_method == AUTH_METHOD_PASSWORD and not password:
        return None, "Password is required for password authentication."
    if auth_method == AUTH_METHOD_KEY and not private_key.strip():
        return None, "Private key is required for key authentication."
    try:
        port = int(credential.get("port") or 22)
    except (TypeError, ValueError):
        return None, "SSH port must be a number."
    if port < 1 or port > 65535:
        return None, "SSH port must be between 1 and 65535."
    return {
        "username": username,
        "port": port,
        "auth_method": auth_method,
        "password": password,
        "private_key": private_key,
        "known_host_fingerprint": fingerprint,
    }, None


def one_shot_payload(data: dict) -> dict:
    """Build the proxbox-api ``one_shot_credential`` body from validated data."""
    payload = {
        "username": data["username"],
        "port": data["port"],
        "known_host_fingerprint": data["known_host_fingerprint"],
    }
    if data["auth_method"] == AUTH_METHOD_KEY:
        payload["private_key"] = data["private_key"]
    else:
        payload["password"] = data["password"]
    return payload
