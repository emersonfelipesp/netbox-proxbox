"""Shared sensitive-field registry for NetBox ObjectChange snapshots."""

from __future__ import annotations

from typing import Any

MASKED_SECRET = "********"

# Include ciphertext and provider references: a changelog reader must not gain
# access to recoverable material or an alternate credential lookup identifier.
SENSITIVE_OBJECTCHANGE_FIELDS: dict[str, frozenset[str]] = {
    "proxboxpluginsettings": frozenset({"encryption_key"}),
    "proxmoxendpoint": frozenset(
        {
            "password",
            "password_enc",
            "token_value",
            "token_value_enc",
            "ssh_password",
            "ssh_password_enc",
            "ssh_private_key",
            "ssh_private_key_enc",
            "openbao_password_credential_uuid",
            "openbao_token_credential_uuid",
            "openbao_ssh_password_credential_uuid",
            "openbao_ssh_keypair_credential_uuid",
        }
    ),
    "netboxendpoint": frozenset({"token_key", "token_secret"}),
    "fastapiendpoint": frozenset(
        {"token", "token_enc", "openbao_token_credential_uuid"}
    ),
    "pbsendpoint": frozenset(
        {"token_secret", "token_secret_enc", "openbao_token_credential_uuid"}
    ),
    "pdmendpoint": frozenset(
        {"token_secret", "token_secret_enc", "openbao_token_credential_uuid"}
    ),
    "nodesshcredential": frozenset(
        {
            "password",
            "password_enc",
            "private_key",
            "private_key_enc",
            "openbao_password_credential_uuid",
            "openbao_keypair_credential_uuid",
        }
    ),
    "firecrackerhost": frozenset(
        {"agent_token", "agent_token_enc", "openbao_agent_token_credential_uuid"}
    ),
    "proxmoxvmcloudinit": frozenset(
        {
            "password",
            "private_key",
            "sshkeys_enc",
            "credential_reference_id",
            "openbao_password_credential_uuid",
            "openbao_keypair_credential_uuid",
        }
    ),
    "proxmoxmetricsinfluxdb": frozenset({"query_token_enc"}),
}


def redact_snapshot_data(model_label: str, data: dict[str, Any]) -> dict[str, Any]:
    """Copy a snapshot and mask configured values without resolving any secret."""
    redacted = dict(data)
    model_name = model_label.lower().rsplit(".", 1)[-1]
    for field_name in SENSITIVE_OBJECTCHANGE_FIELDS.get(model_name, ()):
        if field_name in redacted and redacted[field_name]:
            redacted[field_name] = MASKED_SECRET
    return redacted
