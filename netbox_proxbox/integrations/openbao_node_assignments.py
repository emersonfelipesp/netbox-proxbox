"""Node SSH material and device assignments inside the provider transaction."""

from __future__ import annotations

from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.views.decorators.debug import sensitive_variables

from .openbao_node_pending import SLOTS, PendingCredential
from .openbao_node_transaction import NodeMaterialContext


def _require_scope(instance: Any, actor: Any, action: str) -> None:
    allowed = (
        type(instance).objects.restrict(actor, action).filter(pk=instance.pk).exists()
    )
    if not allowed:
        raise PermissionDenied(
            "OpenBao object permission does not permit this node credential operation."
        )


def _credential_for_slot(
    context: NodeMaterialContext,
    owner: Any,
    reference_field: str,
) -> Any | None:
    reference = getattr(owner, reference_field)
    if reference is None:
        return None
    credential = context.credentials.get(str(reference))
    if credential is None:
        raise ValidationError(
            "The node SSH credential was not declared before persistence."
        )
    if credential.credential_type != SLOTS[reference_field].credential_type:
        raise ValidationError(
            "The node SSH credential type does not match its storage slot."
        )
    return credential


def _credential_name(owner: Any, reference_field: str) -> str:
    label = str(getattr(owner, "node", "") or "Proxmox node").strip()
    owner_id = getattr(owner, "pk", None)
    suffix = f" (nb:{owner_id})" if owner_id else ""
    kind = (
        "password"
        if SLOTS[reference_field].material_field == "password"
        else "key pair"
    )
    return f"Proxbox {label}{suffix} — SSH {kind}"


def _new_credential(
    context: NodeMaterialContext,
    owner: Any,
    reference_field: str,
) -> Any:
    from netbox_openbao.models import Credential

    return Credential(
        name=_credential_name(owner, reference_field),
        credential_type=SLOTS[reference_field].credential_type,
        policy=context.policy,
        engine=context.policy.engine,
    )


@sensitive_variables()
def _write_material(credential: Any, intent: PendingCredential, *, actor: Any) -> Any:
    from netbox_openbao.choices import AccessActionChoices
    from netbox_openbao.services import enforce_policy_access, store_credential

    creating = credential.pk is None
    if creating and not actor.has_perm("netbox_openbao.add_credential"):
        raise PermissionDenied(
            "Creating node SSH material requires OpenBao credential add permission."
        )
    if not creating:
        _require_scope(credential, actor, "rotate")
    if credential.staged_kv_version is not None:
        raise ValidationError(
            "Complete the staged credential rotation before replacing node material."
        )
    enforce_policy_access(credential, actor)
    cas = credential.kv_version or 0

    def persist(metadata: dict[str, Any]) -> Any:
        for name, value in metadata.items():
            setattr(credential, name, value)
        credential.full_clean()
        credential.save()
        if not creating:
            _require_scope(credential, actor, "rotate")
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
def apply_node_material(
    context: NodeMaterialContext,
    owner: Any,
    pending: dict[str, PendingCredential],
    *,
    actor: Any,
) -> None:
    """Write declared slots with CAS; clear only this owner's reference."""
    if owner.pk is None:
        raise ValidationError("Persist the node SSH owner before credential material.")
    context.admit(owner)
    for reference_field, intent in pending.items():
        if getattr(owner, reference_field) != intent.expected_uuid:
            raise ValidationError(
                "Node SSH credential intent no longer matches its original reference."
            )
        credential = _credential_for_slot(context, owner, reference_field)
        if intent.payload is None:
            setattr(owner, reference_field, None)
            continue
        if credential is None:
            credential = _new_credential(context, owner, reference_field)
        credential = _write_material(credential, intent, actor=actor)
        context.credentials[str(credential.uuid)] = credential
        setattr(owner, reference_field, credential.uuid)


def _selected_reference(owner: Any) -> str:
    from netbox_proxbox.models.ssh_credential import (
        AUTH_METHOD_KEY,
        AUTH_METHOD_PASSWORD,
    )

    selected = {
        AUTH_METHOD_PASSWORD: "openbao_password_credential_uuid",
        AUTH_METHOD_KEY: "openbao_keypair_credential_uuid",
    }.get(owner.auth_method)
    if selected is None:
        raise ValidationError("Unsupported node SSH authentication method.")
    return selected


def _owned_credential_ids(context: NodeMaterialContext, owner: Any) -> set[int]:
    owners = [owner]
    previous = context.owners.get(owner.pk)
    if previous is not None:
        owners.append(previous)
    result = set()
    for candidate in owners:
        for reference_field in SLOTS:
            credential = _credential_for_slot(context, candidate, reference_field)
            if credential is not None:
                result.add(credential.pk)
    return result


def _owned_assignment_rows(
    context: NodeMaterialContext,
    owned_ids: set[int],
    device_ids: set[int],
) -> list[Any]:
    from netbox_openbao.models import CredentialAssignment

    if not owned_ids or not device_ids:
        return []
    return list(
        CredentialAssignment.objects.select_for_update()
        .filter(assigned_object_type=context.content_type)
        .filter(
            credential_id__in=owned_ids,
            assigned_object_id__in=device_ids,
            purpose="login",
            is_primary=True,
        )
        .order_by("pk")
    )


def _target_assignment_rows(
    context: NodeMaterialContext,
    device_id: int,
) -> list[Any]:
    from netbox_openbao.models import CredentialAssignment

    return list(
        CredentialAssignment.objects.select_for_update()
        .filter(
            assigned_object_type=context.content_type,
            assigned_object_id=device_id,
            purpose="login",
        )
        .order_by("pk")
    )


def _desired_assignment(
    context: NodeMaterialContext,
    owner: Any,
) -> tuple[int, int] | None:
    device_id = context.device_id(owner)
    if device_id is None:
        return None
    credential = _credential_for_slot(context, owner, _selected_reference(owner))
    if credential is None:
        return None
    return credential.pk, device_id


def _save_assignment(assignment: Any, actor: Any, *, creating: bool) -> None:
    if creating and not actor.has_perm("netbox_openbao.add_credentialassignment"):
        raise PermissionDenied(
            "Creating a node credential assignment requires add permission."
        )
    if not creating:
        _require_scope(assignment, actor, "change")
    assignment.full_clean()
    assignment.save()
    if not creating:
        _require_scope(assignment, actor, "change")


def _refuse_conflicting_primary(
    rows: list[Any],
    owned_ids: set[int],
    desired: tuple[int, int],
) -> None:
    credential_id, device_id = desired
    conflict = next(
        (
            row
            for row in rows
            if row.assigned_object_id == device_id
            and row.purpose == "login"
            and row.is_primary
            and row.credential_id not in owned_ids
        ),
        None,
    )
    if conflict is not None:
        raise ValidationError(
            "Another credential is already primary for this device login purpose."
        )


def _remove_old_primaries(
    context: NodeMaterialContext,
    owner: Any,
    rows: list[Any],
    owned_ids: set[int],
    desired: tuple[int, int] | None,
    actor: Any,
) -> None:
    for assignment in rows:
        current = (assignment.credential_id, assignment.assigned_object_id)
        owned = (
            assignment.credential_id in owned_ids
            and assignment.purpose == "login"
            and assignment.is_primary
        )
        shared = context.assignment_selected_elsewhere(
            owner,
            assignment.credential_id,
            assignment.assigned_object_id,
        )
        if owned and current != desired and not shared:
            _require_scope(assignment, actor, "delete")
            assignment.delete()


def _ensure_primary(
    context: NodeMaterialContext,
    rows: list[Any],
    desired: tuple[int, int],
    actor: Any,
) -> None:
    from netbox_openbao.models import CredentialAssignment

    credential_id, device_id = desired
    assignment = next(
        (
            row
            for row in rows
            if row.credential_id == credential_id
            and row.assigned_object_id == device_id
            and row.purpose == "login"
        ),
        None,
    )
    creating = assignment is None
    if creating:
        assignment = CredentialAssignment(
            credential_id=credential_id,
            purpose="login",
            assigned_object_type=context.content_type,
            assigned_object_id=device_id,
        )
    if not assignment.enabled:
        raise ValidationError(
            "A disabled node credential assignment cannot be enabled implicitly."
        )
    if creating or not assignment.is_primary:
        assignment.is_primary = True
        _save_assignment(assignment, actor, creating=creating)


def reconcile_node_assignment(
    context: NodeMaterialContext,
    owner: Any,
    *,
    actor: Any,
) -> None:
    """Keep one primary device login while preserving every unrelated row."""
    desired = _desired_assignment(context, owner)
    owned_ids = _owned_credential_ids(context, owner)
    owner_device_ids = context.owner_device_ids(owner)
    rows = _owned_assignment_rows(context, owned_ids, owner_device_ids)
    if desired is not None:
        target_rows = _target_assignment_rows(context, desired[1])
        _refuse_conflicting_primary(target_rows, owned_ids, desired)
        rows = list({row.pk: row for row in (*rows, *target_rows)}.values())
    _remove_old_primaries(context, owner, rows, owned_ids, desired, actor)
    if desired is not None:
        _ensure_primary(context, rows, desired, actor)


def remove_node_assignments(
    context: NodeMaterialContext,
    owner: Any,
    *,
    actor: Any,
) -> None:
    """Delete only primary login rows owned through this credential's UUIDs."""
    owned_ids = _owned_credential_ids(context, owner)
    rows = _owned_assignment_rows(
        context,
        owned_ids,
        context.owner_device_ids(owner),
    )
    _remove_old_primaries(context, owner, rows, owned_ids, None, actor)
