"""Instance-local, network-free intent for a node SSH credential save."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from django.views.decorators.debug import sensitive_variables


@dataclass(frozen=True)
class CredentialSlot:
    credential_type: str
    purpose: str
    material_field: str


SLOTS = {
    "openbao_password_credential_uuid": CredentialSlot(
        "ssh-password", "login", "password"
    ),
    "openbao_keypair_credential_uuid": CredentialSlot(
        "ssh-keypair", "login", "private_key"
    ),
}
_ATTRIBUTE = "_proxbox_openbao_node_pending"


@dataclass(frozen=True)
class PendingCredential:
    """A reference-bound mutation whose representation hides material."""

    expected_uuid: Any
    payload: dict[str, str] | None = field(repr=False)
    user: Any = field(default=None, repr=False)
    request: Any = field(default=None, repr=False)


@sensitive_variables()
def queue_credential(
    credential: Any,
    reference_field: str,
    payload: dict[str, str] | None,
    *,
    user: Any = None,
    request: Any = None,
) -> None:
    """Replace one local intent while retaining its original UUID binding."""
    if reference_field not in SLOTS:
        raise ValueError("Unsupported node SSH credential reference.")
    pending = getattr(credential, _ATTRIBUTE, {})
    previous = pending.get(reference_field)
    expected = (
        previous.expected_uuid
        if previous is not None
        else getattr(credential, reference_field, None)
    )
    pending[reference_field] = PendingCredential(
        expected,
        None if payload is None else dict(payload),
        user,
        request,
    )
    setattr(credential, _ATTRIBUTE, pending)


@sensitive_variables()
def pending_credential(
    credential: Any, reference_field: str
) -> PendingCredential | None:
    """Return a detached intent for read-after-set without a provider read."""
    pending = getattr(credential, _ATTRIBUTE, {}).get(reference_field)
    if pending is None:
        return None
    return PendingCredential(
        pending.expected_uuid,
        None if pending.payload is None else dict(pending.payload),
        pending.user,
        pending.request,
    )


@sensitive_variables()
def consume_credentials(credential: Any) -> dict[str, PendingCredential]:
    """Transfer one-use material off the instance before persistence."""
    return credential.__dict__.pop(_ATTRIBUTE, {})
