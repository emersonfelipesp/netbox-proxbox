"""Endpoint credential writes and relations inside the provider transaction."""

from __future__ import annotations

from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.views.decorators.debug import sensitive_variables

from .openbao_pending import SLOTS, PendingCredential
from .openbao_transaction import EndpointMaterialContext


def fresh_material_actor(user: Any = None) -> Any:
    """Reload the actor so permission caches cannot predate graph locking."""
    from django.contrib.auth import get_user_model

    from .openbao import _openbao_actor

    if user is not None and not getattr(user, "is_authenticated", False):
        raise PermissionDenied("Authenticated OpenBao credential access is required.")
    selected = _openbao_actor(user)
    actor = get_user_model().objects.filter(pk=selected.pk, is_active=True).first()
    if actor is None:
        raise PermissionDenied("An active OpenBao credential actor is required.")
    return actor


def resolve_transaction_actor(
    pending: dict[str, PendingCredential],
    fallback_user: Any = None,
) -> Any:
    """Resolve one active actor for every mutation in the owner transaction."""
    from .openbao_node_transaction import current_node_request_actor

    candidates = [intent.user for intent in pending.values()]
    if not candidates:
        candidates = [fallback_user or current_node_request_actor()]
    actors = [fresh_material_actor(candidate) for candidate in candidates]
    if len({actor.pk for actor in actors}) != 1:
        raise PermissionDenied(
            "All OpenBao credential changes in one save require the same actor."
        )
    return actors[0]


def _require_scope(instance: Any, actor: Any, action: str) -> None:
    allowed = (
        type(instance).objects.restrict(actor, action).filter(pk=instance.pk).exists()
    )
    if not allowed:
        raise PermissionDenied(
            "OpenBao object permission does not permit this credential operation."
        )


def _credential_for_slot(
    context: EndpointMaterialContext,
    endpoint: Any,
    reference_field: str,
) -> Any | None:
    reference = getattr(endpoint, reference_field)
    if reference is None:
        return None
    credential = context.credentials.get(str(reference))
    if credential is None:
        raise ValidationError(
            "The endpoint credential was not declared before persistence."
        )
    if credential.credential_type != SLOTS[reference_field].credential_type:
        raise ValidationError(
            "The endpoint credential type does not match its assigned purpose."
        )
    return credential


def _new_credential(
    context: EndpointMaterialContext,
    endpoint: Any,
    reference_field: str,
) -> Any:
    from netbox_openbao.models import Credential

    from .openbao import _credential_name

    slot = SLOTS[reference_field]
    return Credential(
        name=_credential_name(endpoint, slot.purpose),
        credential_type=slot.credential_type,
        policy=context.policy,
        engine=context.policy.engine,
    )


@sensitive_variables()
def _write_material(credential: Any, intent: PendingCredential, *, actor: Any) -> Any:
    from netbox_openbao.choices import AccessActionChoices
    from netbox_openbao.services import enforce_policy_access, store_credential

    creating = credential.pk is None
    action = "add" if creating else "rotate"
    if creating and not actor.has_perm("netbox_openbao.add_credential"):
        raise PermissionDenied(
            "Creating endpoint material requires OpenBao credential add permission."
        )
    if not creating:
        _require_scope(credential, actor, "rotate")
    if credential.staged_kv_version is not None:
        raise ValidationError(
            "Complete the staged credential rotation before replacing endpoint material."
        )
    enforce_policy_access(credential, actor)
    cas = credential.kv_version or 0

    def persist(metadata: dict[str, Any]) -> Any:
        for name, value in metadata.items():
            setattr(credential, name, value)
        credential.full_clean()
        credential.save()
        if not creating:
            _require_scope(credential, actor, action)
        return credential

    stored, _version = store_credential(
        persist,
        credential.credential_type,
        intent.payload,
        cas=cas,
        user=actor,
        request=intent.request,
        subject=credential,
        action=(
            AccessActionChoices.ACTION_WRITE
            if creating
            else AccessActionChoices.ACTION_ROTATE
        ),
        prelocked=True,
    )
    return stored


@sensitive_variables()
def apply_endpoint_material(
    context: EndpointMaterialContext,
    endpoint: Any,
    pending: dict[str, PendingCredential],
    *,
    actor: Any,
) -> None:
    """Write declared slots with CAS; clear only this owner's reference."""
    if endpoint.pk is None:
        raise ValidationError("Persist the endpoint owner before credential material.")
    context.admit(endpoint)
    for reference_field, intent in pending.items():
        if getattr(endpoint, reference_field) != intent.expected_uuid:
            raise ValidationError(
                "Endpoint credential intent no longer matches its original reference."
            )
        credential = _credential_for_slot(context, endpoint, reference_field)
        if intent.payload is None:
            setattr(endpoint, reference_field, None)
            continue
        if credential is None:
            credential = _new_credential(context, endpoint, reference_field)
        credential = _write_material(credential, intent, actor=actor)
        context.credentials[str(credential.uuid)] = credential
        setattr(endpoint, reference_field, credential.uuid)


def _is_primary(endpoint: Any, reference_field: str) -> bool:
    from netbox_proxbox.models.ssh_credential import (
        AUTH_METHOD_KEY,
        AUTH_METHOD_PASSWORD,
        SSH_CRED_SOURCE_DEDICATED,
    )

    if SLOTS[reference_field].purpose != "console":
        return True
    if endpoint.ssh_credential_source != SSH_CRED_SOURCE_DEDICATED:
        return False
    selected = {
        AUTH_METHOD_PASSWORD: "openbao_ssh_password_credential_uuid",
        AUTH_METHOD_KEY: "openbao_ssh_keypair_credential_uuid",
    }.get(endpoint.ssh_auth_method)
    if selected is None:
        raise ValidationError("Unsupported endpoint SSH authentication method.")
    return reference_field == selected


def _desired_assignments(
    context: EndpointMaterialContext,
    endpoint: Any,
) -> dict[tuple[int, str], bool]:
    desired = {}
    for reference_field, slot in SLOTS.items():
        credential = _credential_for_slot(context, endpoint, reference_field)
        if credential is not None:
            desired[(credential.pk, slot.purpose)] = _is_primary(
                endpoint, reference_field
            )
    return desired


def _previous_assignments(
    context: EndpointMaterialContext,
    endpoint: Any,
) -> set[tuple[int, str]]:
    previous = context.endpoints.get(endpoint.pk)
    if previous is None:
        return set()
    result = set()
    for reference_field, slot in SLOTS.items():
        credential = _credential_for_slot(context, previous, reference_field)
        if credential is not None:
            result.add((credential.pk, slot.purpose))
    return result


def _save_assignment(assignment: Any, actor: Any, *, creating: bool) -> None:
    if creating and not actor.has_perm("netbox_openbao.add_credentialassignment"):
        raise PermissionDenied(
            "Creating an endpoint credential assignment requires add permission."
        )
    if not creating:
        _require_scope(assignment, actor, "change")
    assignment.full_clean()
    assignment.save()
    if not creating:
        _require_scope(assignment, actor, "change")


def _remove_or_demote_owned(
    rows: list[Any],
    previous: set[tuple[int, str]],
    desired: dict[tuple[int, str], bool],
    actor: Any,
) -> None:
    for assignment in rows:
        key = (assignment.credential_id, assignment.purpose)
        if key not in previous:
            continue
        if key not in desired:
            _require_scope(assignment, actor, "delete")
            assignment.delete()
        elif assignment.is_primary and not desired[key]:
            assignment.is_primary = False
            _save_assignment(assignment, actor, creating=False)


def reconcile_endpoint_assignments(
    context: EndpointMaterialContext,
    endpoint: Any,
    *,
    actor: Any,
) -> None:
    """Reconcile only the four owned relations, preserving unrelated rows."""
    from netbox_openbao.models import CredentialAssignment

    desired = _desired_assignments(context, endpoint)
    previous = _previous_assignments(context, endpoint)
    rows = list(
        CredentialAssignment.objects.select_for_update()
        .filter(
            assigned_object_type=context.content_type,
            assigned_object_id=endpoint.pk,
        )
        .order_by("pk")
    )
    _remove_or_demote_owned(rows, previous, desired, actor)
    indexed = {(row.credential_id, row.purpose): row for row in rows}
    for (credential_id, purpose), primary in desired.items():
        assignment = indexed.get((credential_id, purpose))
        creating = assignment is None
        if creating:
            assignment = CredentialAssignment(
                credential_id=credential_id,
                purpose=purpose,
                assigned_object_type=context.content_type,
                assigned_object_id=endpoint.pk,
            )
        if not assignment.enabled:
            raise ValidationError(
                "A disabled credential assignment cannot be enabled implicitly."
            )
        if creating or assignment.is_primary != primary:
            assignment.is_primary = primary
            _save_assignment(assignment, actor, creating=creating)


def remove_endpoint_assignments(
    context: EndpointMaterialContext,
    endpoint: Any,
    *,
    actor: Any,
) -> None:
    """Delete every assignment targeting an endpoint before owner deletion."""
    from netbox_openbao.models import CredentialAssignment

    rows = CredentialAssignment.objects.select_for_update().filter(
        assigned_object_type=context.content_type,
        assigned_object_id=endpoint.pk,
    )
    for assignment in rows.order_by("pk"):
        _require_scope(assignment, actor, "delete")
        assignment.delete()
