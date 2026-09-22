"""Instance-local, network-free intent for an endpoint's next save."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CredentialSlot:
    credential_type: str
    purpose: str
    material_field: str


SLOTS = {
    "openbao_password_credential_uuid": CredentialSlot("password", "login", "password"),
    "openbao_token_credential_uuid": CredentialSlot("api-token", "api", "token"),
    "openbao_ssh_password_credential_uuid": CredentialSlot(
        "ssh-password", "console", "password"
    ),
    "openbao_ssh_keypair_credential_uuid": CredentialSlot(
        "ssh-keypair", "console", "private_key"
    ),
}
_ATTRIBUTE = "_proxbox_openbao_pending"


@dataclass(frozen=True)
class PendingCredential:
    """A reference-bound mutation whose representation hides material."""

    expected_uuid: Any
    payload: dict[str, str] | None = field(repr=False)
    user: Any = field(default=None, repr=False)
    request: Any = field(default=None, repr=False)


def queue_credential(
    endpoint: Any,
    reference_field: str,
    payload: dict[str, str] | None,
    *,
    user: Any = None,
    request: Any = None,
) -> None:
    """Replace one local intent while retaining its original reference binding."""
    if reference_field not in SLOTS:
        raise ValueError("Unsupported endpoint credential reference.")
    pending = getattr(endpoint, _ATTRIBUTE, {})
    previous = pending.get(reference_field)
    expected = (
        previous.expected_uuid
        if previous is not None
        else getattr(endpoint, reference_field, None)
    )
    pending[reference_field] = PendingCredential(
        expected,
        None if payload is None else dict(payload),
        user,
        request,
    )
    setattr(endpoint, _ATTRIBUTE, pending)


def pending_credential(endpoint: Any, reference_field: str) -> PendingCredential | None:
    """Return a detached intent for read-after-set without a backend read."""
    pending = getattr(endpoint, _ATTRIBUTE, {}).get(reference_field)
    if pending is None:
        return None
    return PendingCredential(
        pending.expected_uuid,
        None if pending.payload is None else dict(pending.payload),
        pending.user,
        pending.request,
    )


def consume_credentials(endpoint: Any) -> dict[str, PendingCredential]:
    """Transfer one-use material off the instance before persistence."""
    return endpoint.__dict__.pop(_ATTRIBUTE, {})
