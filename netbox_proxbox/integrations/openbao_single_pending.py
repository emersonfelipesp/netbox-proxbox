"""Instance-local intents for one-secret OpenBao owners."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class SingleSecretSpec:
    """Typed storage contract for one owner model and one secret."""

    model_name: str
    reference_field: str
    encrypted_field: str
    material_field: str
    credential_type: str
    purpose: str
    label: str


SPECS = {
    "fastapiendpoint": SingleSecretSpec(
        "fastapiendpoint",
        "openbao_token_credential_uuid",
        "token_enc",
        "token",
        "api-token",
        "api",
        "FastAPI token",
    ),
    "pbsendpoint": SingleSecretSpec(
        "pbsendpoint",
        "openbao_token_credential_uuid",
        "token_secret_enc",
        "token",
        "api-token",
        "api",
        "PBS API token",
    ),
    "pdmendpoint": SingleSecretSpec(
        "pdmendpoint",
        "openbao_token_credential_uuid",
        "token_secret_enc",
        "token",
        "api-token",
        "api",
        "PDM API token",
    ),
    "firecrackerhost": SingleSecretSpec(
        "firecrackerhost",
        "openbao_agent_token_credential_uuid",
        "agent_token_enc",
        "token",
        "api-token",
        "agent",
        "Firecracker agent token",
    ),
}
_ATTRIBUTE = "_proxbox_openbao_single_pending"


@dataclass(frozen=True)
class PendingSingleSecret:
    """A reference-bound write whose representation hides its material."""

    expected_uuid: Any
    payload: dict[str, str] | None = field(repr=False)
    user: Any = field(default=None, repr=False)
    request: Any = field(default=None, repr=False)


def spec_for(owner_or_model: Any) -> SingleSecretSpec:
    """Return the declared contract for an owner instance or model."""
    meta = owner_or_model._meta
    try:
        return SPECS[meta.model_name]
    except KeyError as exc:
        raise ValueError("Unsupported single-secret credential owner.") from exc


def queue_single_secret(
    owner: Any,
    payload: dict[str, str] | None,
    *,
    user: Any = None,
    request: Any = None,
) -> None:
    """Replace the next-save intent while retaining the original UUID binding."""
    spec = spec_for(owner)
    previous = getattr(owner, _ATTRIBUTE, None)
    expected = (
        previous.expected_uuid
        if previous is not None
        else getattr(owner, spec.reference_field, None)
    )
    setattr(
        owner,
        _ATTRIBUTE,
        PendingSingleSecret(
            expected,
            None if payload is None else dict(payload),
            user,
            request,
        ),
    )


def pending_single_secret(owner: Any) -> PendingSingleSecret | None:
    """Return a detached read-after-set intent without contacting the provider."""
    pending = getattr(owner, _ATTRIBUTE, None)
    if pending is None:
        return None
    return PendingSingleSecret(
        pending.expected_uuid,
        None if pending.payload is None else dict(pending.payload),
        pending.user,
        pending.request,
    )


def consume_single_secret(owner: Any) -> PendingSingleSecret | None:
    """Transfer the one-use intent off an instance before persistence."""
    return owner.__dict__.pop(_ATTRIBUTE, None)
