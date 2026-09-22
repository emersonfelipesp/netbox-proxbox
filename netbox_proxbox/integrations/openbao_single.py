"""Storage and secret-free assignment metadata for one-secret owners."""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError
from django.views.decorators.debug import sensitive_variables

from netbox_proxbox.choices import CredentialStorageBackendChoices

from .openbao_single_pending import (
    pending_single_secret,
    queue_single_secret,
    spec_for,
)


def owner_uses_openbao_storage(owner: Any) -> bool:
    """Return the effective plugin-wide backend for a single-secret owner."""
    from .openbao import effective_credential_storage_backend

    spec_for(owner)
    return (
        effective_credential_storage_backend()
        == CredentialStorageBackendChoices.OPENBAO
    )


@sensitive_variables()
def store_single_secret(
    owner: Any,
    plaintext: str,
    *,
    user: Any = None,
    request: Any = None,
) -> None:
    """Queue provider material without changing the durable reference."""
    from .openbao import validate_openbao_storage_available

    validate_openbao_storage_available(storage_backend="openbao")
    spec = spec_for(owner)
    from netbox_proxbox.services.encryption_recovery import (
        mark_encrypted_fields_for_write,
    )

    mark_encrypted_fields_for_write(owner, spec.encrypted_field)
    queue_single_secret(
        owner,
        {spec.material_field: plaintext},
        user=user,
        request=request,
    )


def clear_single_secret(owner: Any, *, user: Any = None, request: Any = None) -> None:
    """Queue owner-only reference and assignment cleanup."""
    queue_single_secret(owner, None, user=user, request=request)


def _pending_secret_value(owner: Any, spec: Any) -> str | None:
    pending = pending_single_secret(owner)
    if pending is None or pending.payload is None:
        return None
    return str(pending.payload.get(spec.material_field, ""))


def _active_fastapi_transition(owner: Any) -> bool:
    from .openbao_single_transaction import current_single_secret_context

    context = current_single_secret_context()
    if context is None or owner._meta.model_name != "fastapiendpoint":
        return False
    declared = context.intent_for(owner)
    admitted_new = context.new_instances.get(id(owner)) is owner
    return admitted_new or getattr(declared, "payload", None) is not None


def _single_secret_credential(reference: Any, spec: Any) -> Any:
    from .openbao import _credential_for_uuid

    credential = _credential_for_uuid(reference)
    if credential is None:
        raise ValidationError(
            f"The selected OpenBao {spec.label} reference cannot be resolved."
        )
    if credential.credential_type != spec.credential_type:
        raise ValidationError(
            f"The selected OpenBao {spec.label} has an incompatible type."
        )
    return credential


@sensitive_variables()
def _revealed_secret_value(credential: Any, spec: Any, user: Any) -> str:
    from .openbao import reveal_credential_material

    if user is None:
        from .openbao_single_transaction import current_single_secret_actor

        user = current_single_secret_actor()
    material = reveal_credential_material(credential, user=user)
    value = material.get(spec.material_field)
    if value in (None, ""):
        raise ValidationError(
            f"The selected OpenBao {spec.label} material is unavailable."
        )
    return str(value)


@sensitive_variables()
def resolve_single_secret(owner: Any, *, user: Any = None) -> str:
    """Resolve selected provider material and never fall back to Fernet."""
    spec = spec_for(owner)
    pending = _pending_secret_value(owner, spec)
    if pending is not None:
        return pending
    reference = getattr(owner, spec.reference_field, None)
    if reference is None:
        if _active_fastapi_transition(owner):
            return ""
        raise ValidationError(f"The selected OpenBao {spec.label} is not configured.")
    credential = _single_secret_credential(reference, spec)
    return _revealed_secret_value(credential, spec, user)


def credential_assignment_lookup(owner: Any) -> dict[str, str] | None:
    """Return vendor-neutral selectors for the owner's primary assignment."""
    if owner.pk is None:
        return None
    spec = spec_for(owner)
    return {
        "assigned_object_type": owner._meta.label_lower,
        "assigned_object_id": str(owner.pk),
        "purpose": spec.purpose,
    }


def credential_assignment_readiness(owner: Any) -> tuple[bool, str]:
    """Check assignment metadata without revealing provider material."""
    if not owner_uses_openbao_storage(owner):
        return True, "Legacy storage does not require a provider assignment."
    lookup = credential_assignment_lookup(owner)
    if lookup is None:
        return False, "Persist the credential owner before checking readiness."
    spec = spec_for(owner)
    reference = getattr(owner, spec.reference_field, None)
    if reference is None:
        return False, "The selected provider credential is not configured."
    try:
        from netbox_openbao.models import CredentialAssignment
    except ImportError:
        return False, "The credential provider is unavailable; restore it before use."
    app_label, model = lookup["assigned_object_type"].split(".", 1)
    matches = CredentialAssignment.objects.filter(
        credential__uuid=reference,
        assigned_object_type__app_label=app_label,
        assigned_object_type__model=model,
        assigned_object_id=int(lookup["assigned_object_id"]),
        purpose=lookup["purpose"],
        is_primary=True,
        enabled=True,
    ).count()
    if matches != 1:
        return False, "The selected provider credential assignment is not ready."
    return True, "The selected provider credential assignment is ready."
