"""Persist one-secret owner material through the provider transaction."""

from __future__ import annotations

from functools import partial, wraps
from typing import Any, Callable

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import router
from django.views.decorators.debug import sensitive_variables

from .openbao_single_pending import (
    PendingSingleSecret,
    consume_single_secret,
    queue_single_secret,
    spec_for,
)
from .openbao_single_transaction import (
    SingleSecretMaterialContext,
    current_single_secret_actor,
    current_single_secret_context,
    current_single_secret_request,
    single_secret_material_transaction,
)

_MISSING = object()


def _database_alias(owner: Any, kwargs: dict[str, Any]) -> str:
    return kwargs.get("using") or router.db_for_write(type(owner), instance=owner)


def _restore(owner: Any, reference: Any, ciphertext: Any) -> None:
    spec = spec_for(owner)
    setattr(owner, spec.reference_field, reference)
    setattr(owner, spec.encrypted_field, ciphertext)


def _restore_save_state(
    owner: Any,
    *,
    primary_key: Any,
    adding: bool,
    database: Any,
    loaded_signature: Any,
) -> None:
    owner.pk = primary_key
    owner._state.adding = adding
    owner._state.db = database
    if loaded_signature is _MISSING:
        owner.__dict__.pop("_backend_key_loaded_signature", None)
        return
    owner._backend_key_loaded_signature = loaded_signature


def _persist_material_fields(owner: Any, original: Callable, spec: Any) -> None:
    fields = [spec.reference_field, spec.encrypted_field]
    if owner._meta.model_name == "fastapiendpoint":
        super(type(owner), owner).save(update_fields=fields, using="default")
        owner._backend_key_loaded_signature = owner._backend_key_persisted_signature()
        return
    original(owner, update_fields=fields, using="default")


def _require_scope(instance: Any, actor: Any, action: str) -> None:
    allowed = (
        type(instance).objects.restrict(actor, action).filter(pk=instance.pk).exists()
    )
    if not allowed:
        raise PermissionDenied(
            "OpenBao object permission does not permit this credential operation."
        )


def _fresh_actor(user: Any = None) -> Any:
    from django.contrib.auth import get_user_model

    from .openbao import _openbao_actor

    if user is not None and not getattr(user, "is_authenticated", False):
        raise PermissionDenied("Authenticated OpenBao credential access is required.")
    selected = _openbao_actor(user)
    actor = get_user_model().objects.filter(pk=selected.pk, is_active=True).first()
    if actor is None:
        raise PermissionDenied("An active OpenBao credential actor is required.")
    return actor


def _resolve_actor(intent: PendingSingleSecret | None, owner: Any) -> Any:
    candidate = intent.user if intent is not None else None
    candidate = candidate or getattr(owner, "_openbao_actor_user", None)
    candidate = candidate or current_single_secret_actor()
    return _fresh_actor(candidate)


def _credential_for_owner(
    context: SingleSecretMaterialContext, owner: Any
) -> Any | None:
    spec = spec_for(owner)
    reference = getattr(owner, spec.reference_field, None)
    if reference is None:
        return None
    credential = context.credentials.get(str(reference))
    if credential is None:
        raise ValidationError(
            "The owner credential was not declared before persistence."
        )
    if credential.credential_type != spec.credential_type:
        raise ValidationError(
            "The owner credential type does not match its assigned purpose."
        )
    return credential


def _credential_name(owner: Any) -> str:
    spec = spec_for(owner)
    label = str(getattr(owner, "name", "") or owner._meta.verbose_name).strip()
    suffix = f" (nb:{owner.pk})" if owner.pk else ""
    return f"Proxbox {label}{suffix} — {spec.label}"


def _new_credential(context: SingleSecretMaterialContext, owner: Any) -> Any:
    from netbox_openbao.models import Credential

    spec = spec_for(owner)
    return Credential(
        name=_credential_name(owner),
        credential_type=spec.credential_type,
        policy=context.policy,
        engine=context.policy.engine,
    )


@sensitive_variables()
def _write_material(credential: Any, intent: PendingSingleSecret, *, actor: Any) -> Any:
    from netbox_openbao.choices import AccessActionChoices
    from netbox_openbao.services import enforce_policy_access, store_credential

    creating = credential.pk is None
    if creating and not actor.has_perm("netbox_openbao.add_credential"):
        raise PermissionDenied(
            "Creating credential material requires OpenBao credential add permission."
        )
    if not creating:
        _require_scope(credential, actor, "rotate")
    if credential.staged_kv_version is not None:
        raise ValidationError(
            "Complete the staged credential rotation before replacing material."
        )
    enforce_policy_access(credential, actor)

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
        cas=credential.kv_version or 0,
        user=actor,
        request=intent.request or current_single_secret_request(),
        subject=credential,
        action=(
            AccessActionChoices.ACTION_WRITE
            if creating
            else AccessActionChoices.ACTION_ROTATE
        ),
        prelocked=True,
    )
    return stored


def _save_assignment(assignment: Any, actor: Any, *, creating: bool) -> None:
    if creating and not actor.has_perm("netbox_openbao.add_credentialassignment"):
        raise PermissionDenied(
            "Creating a credential assignment requires add permission."
        )
    if not creating:
        _require_scope(assignment, actor, "change")
    assignment.full_clean()
    assignment.save()
    if not creating:
        _require_scope(assignment, actor, "change")


def _owned_assignments(context: SingleSecretMaterialContext, owner: Any) -> list[Any]:
    context.admit(owner)
    return context.assignments.setdefault((owner._meta.label_lower, int(owner.pk)), [])


def _select_assignment(rows: list[Any], desired_id: int | None, actor: Any) -> Any:
    """Keep at most one desired assignment and remove only this owner's extras."""
    selected = None
    for assignment in list(rows):
        if assignment.credential_id == desired_id and selected is None:
            selected = assignment
            continue
        _require_scope(assignment, actor, "delete")
        assignment.delete()
        rows.remove(assignment)
    return selected


def _ensure_assignment(
    context: SingleSecretMaterialContext,
    owner: Any,
    rows: list[Any],
    selected: Any,
    desired_id: int,
    actor: Any,
) -> None:
    """Create or promote the owner's declared provider assignment."""
    from netbox_openbao.models import CredentialAssignment

    creating = selected is None
    if creating:
        selected = CredentialAssignment(
            credential_id=desired_id,
            purpose=spec_for(owner).purpose,
            assigned_object_type=context.content_type_for(owner),
            assigned_object_id=owner.pk,
        )
    if not selected.enabled:
        raise ValidationError(
            "A disabled credential assignment cannot be enabled implicitly."
        )
    if creating or not selected.is_primary:
        selected.is_primary = True
        _save_assignment(selected, actor, creating=creating)
    if creating:
        rows.append(selected)


def _reconcile_assignment(
    context: SingleSecretMaterialContext, owner: Any, *, actor: Any
) -> None:
    credential = _credential_for_owner(context, owner)
    rows = _owned_assignments(context, owner)
    desired_id = credential.pk if credential is not None else None
    selected = _select_assignment(rows, desired_id, actor)
    if desired_id is None:
        return
    _ensure_assignment(context, owner, rows, selected, desired_id, actor)


@sensitive_variables()
def _apply_material(
    context: SingleSecretMaterialContext,
    owner: Any,
    intent: PendingSingleSecret,
    *,
    actor: Any,
) -> None:
    spec = spec_for(owner)
    if owner.pk is None:
        raise ValidationError("Persist the credential owner before material access.")
    context.admit(owner)
    if getattr(owner, spec.reference_field) != intent.expected_uuid:
        raise ValidationError(
            "The credential intent no longer matches its original reference."
        )
    credential = _credential_for_owner(context, owner)
    if intent.payload is None:
        setattr(owner, spec.reference_field, None)
        setattr(owner, spec.encrypted_field, "")
        return
    if credential is None:
        credential = _new_credential(context, owner)
    credential = _write_material(credential, intent, actor=actor)
    context.credentials[str(credential.uuid)] = credential
    setattr(owner, spec.reference_field, credential.uuid)
    setattr(owner, spec.encrypted_field, "")


def _validate_reference(owner: Any, previous: Any, has_intent: bool) -> None:
    spec = spec_for(owner)
    if has_intent:
        return
    if getattr(owner, spec.reference_field) != getattr(previous, spec.reference_field):
        raise ValidationError(
            "OpenBao credential UUID references cannot be rebound directly."
        )


def _requires_owner(owner: Any, intent: PendingSingleSecret | None) -> bool:
    if intent is not None:
        return True
    if owner.pk is None:
        return owner._meta.model_name == "fastapiendpoint" and bool(owner.enabled)
    spec = spec_for(owner)
    if getattr(owner, spec.reference_field, None) is not None:
        return True
    return _has_owned_assignments(owner)


def _has_owned_assignments(owner: Any) -> bool:
    if owner.pk is None:
        return False
    spec = spec_for(owner)
    reference = getattr(owner, spec.reference_field, None)
    from .openbao import is_netbox_openbao_installed

    if not is_netbox_openbao_installed():
        if reference is not None:
            raise ValidationError(
                "OpenBao references remain, but netbox-openbao is unavailable. "
                "Restore the provider and use the supported cleanup path."
            )
        return False
    try:
        from netbox_openbao.models import CredentialAssignment
    except ImportError as exc:
        if reference is not None:
            raise ValidationError(
                "OpenBao references remain, but netbox-openbao is unavailable. "
                "Restore the provider and use the supported cleanup path."
            ) from exc
        return False
    return CredentialAssignment.objects.filter(
        assigned_object_type__app_label=owner._meta.app_label,
        assigned_object_type__model=owner._meta.model_name,
        assigned_object_id=owner.pk,
        purpose=spec.purpose,
    ).exists()


def _save_legacy_owner(
    owner: Any,
    original: Callable,
    args: tuple,
    kwargs: dict[str, Any],
    intent: PendingSingleSecret | None,
) -> Any:
    """Persist an explicitly legacy owner only when no OpenBao state remains."""
    if intent is not None:
        raise ValidationError(
            "The credential storage selection changed after material was supplied."
        )
    spec = spec_for(owner)
    if getattr(owner, spec.reference_field) is not None or _has_owned_assignments(
        owner
    ):
        raise ValidationError(
            "OpenBao references or assignments remain. Restore OpenBao and use "
            "the supported cleanup path before switching storage backends."
        )
    return original(owner, *args, **kwargs)


def _previous_owner(context: SingleSecretMaterialContext, owner: Any) -> Any | None:
    """Return the prelocked persisted owner, if this is not a create."""
    if owner.pk is None:
        return None
    return context.owners.get((owner._meta.label_lower, int(owner.pk)))


def _expose_fastapi_intent_during_save(
    owner: Any, intent: PendingSingleSecret | None
) -> None:
    """Keep FastAPI's transition getter pointed at its explicit candidate."""
    if owner._meta.model_name != "fastapiendpoint" or intent is None:
        return
    if intent.payload is not None:
        owner._backend_key_token_explicitly_assigned = True
    queue_single_secret(
        owner,
        intent.payload,
        user=intent.user,
        request=intent.request,
    )


@sensitive_variables("plaintext")
def _capture_fastapi_candidate(
    owner: Any,
    intent: PendingSingleSecret | None,
    plaintext: str,
) -> None:
    """Retain a FastAPI-generated candidate as provider write intent."""
    spec = spec_for(owner)
    queue_single_secret(
        owner,
        {spec.material_field: plaintext},
        user=intent.user if intent is not None else current_single_secret_actor(),
        request=(
            intent.request if intent is not None else current_single_secret_request()
        ),
    )


def _call_owner_save(
    owner: Any,
    original: Callable,
    args: tuple,
    kwargs: dict[str, Any],
    intent: PendingSingleSecret | None,
) -> Any:
    """Run FastAPI transitions without creating transient Fernet ciphertext."""
    _expose_fastapi_intent_during_save(owner, intent)
    if owner._meta.model_name != "fastapiendpoint":
        return original(owner, *args, **kwargs)
    from netbox_proxbox.models.primary_secrets import (
        skip_primary_secret_encryption,
    )

    capture = partial(_capture_fastapi_candidate, owner, intent)
    with skip_primary_secret_encryption(capture):
        return original(owner, *args, **kwargs)


@sensitive_variables()
def _fastapi_bootstrap_intent(owner: Any) -> PendingSingleSecret | None:
    """Convert the existing FastAPI bootstrap candidate into provider material."""
    if owner._meta.model_name != "fastapiendpoint":
        return None
    spec = spec_for(owner)
    if getattr(owner, spec.reference_field, None) is not None:
        return None
    plaintext = getattr(owner, "_pending_backend_key", None)
    if plaintext in (None, ""):
        return None
    return PendingSingleSecret(
        expected_uuid=None,
        payload={spec.material_field: str(plaintext)},
        user=current_single_secret_actor(),
        request=current_single_secret_request(),
    )


def _intent_changes_fastapi_material(
    context: SingleSecretMaterialContext,
    owner: Any,
    intent: PendingSingleSecret | None,
    actor: Any,
) -> bool:
    """Avoid rotating an existing FastAPI credential to identical material."""
    if owner._meta.model_name != "fastapiendpoint" or intent is None:
        return True
    if intent.payload is None:
        return True
    credential = _credential_for_owner(context, owner)
    if credential is None:
        return True
    from .openbao import reveal_credential_material

    current = reveal_credential_material(credential, user=actor)
    field = spec_for(owner).material_field
    return current.get(field) != intent.payload.get(field)


def _persist_pending_material(
    context: SingleSecretMaterialContext,
    owner: Any,
    original: Callable,
    spec: Any,
    intent: PendingSingleSecret | None,
    actor: Any,
    *,
    material_changed: bool,
) -> None:
    """Apply material queued before or during the owner's model save."""
    queued = consume_single_secret(owner)
    candidate = intent or queued
    candidate = candidate or _fastapi_bootstrap_intent(owner)
    if candidate is None:
        owner.__dict__.pop("_pending_backend_key", None)
        return
    if not material_changed:
        owner.__dict__.pop("_pending_backend_key", None)
        return
    if owner._meta.model_name != "fastapiendpoint":
        from netbox_proxbox.services.encryption_recovery import (
            mark_encrypted_fields_for_write,
        )

        mark_encrypted_fields_for_write(owner, spec.encrypted_field)
    try:
        _apply_material(context, owner, candidate, actor=actor)
        _persist_material_fields(owner, original, spec)
    except BaseException:
        queue_single_secret(
            owner,
            candidate.payload,
            user=candidate.user,
            request=candidate.request,
        )
        owner.__dict__.pop("_pending_backend_key", None)
        raise
    owner.__dict__.pop("_pending_backend_key", None)


@sensitive_variables()
def save_single_secret_owner(
    owner: Any, original: Callable, args: tuple, kwargs: dict[str, Any]
) -> Any:
    from .openbao_single import owner_uses_openbao_storage

    spec = spec_for(owner)
    intent = consume_single_secret(owner)
    reference = getattr(owner, spec.reference_field)
    ciphertext = getattr(owner, spec.encrypted_field)
    primary_key = owner.pk
    adding = owner._state.adding
    database = owner._state.db
    loaded_signature = owner.__dict__.get("_backend_key_loaded_signature", _MISSING)
    if not owner_uses_openbao_storage(owner):
        return _save_legacy_owner(owner, original, args, kwargs, intent)
    if not _requires_owner(owner, intent) and current_single_secret_context() is None:
        return original(owner, *args, **kwargs)
    if _database_alias(owner, kwargs) != "default":
        raise ValidationError(
            "OpenBao credential material requires the default database transaction owner."
        )
    try:
        new_models = {type(owner)} if owner.pk is None else set()
        with single_secret_material_transaction(
            [owner], new_models=new_models
        ) as context:
            context.admit(owner)
            context.declare_intent(owner, intent)
            previous = _previous_owner(context, owner)
            if previous is not None:
                _validate_reference(owner, previous, intent is not None)
            actor = _resolve_actor(intent, owner)
            material_changed = _intent_changes_fastapi_material(
                context, owner, intent, actor
            )
            result = _call_owner_save(owner, original, args, kwargs, intent)
            _persist_pending_material(
                context,
                owner,
                original,
                spec,
                intent,
                actor,
                material_changed=material_changed,
            )
            _reconcile_assignment(context, owner, actor=actor)
            return result
    except BaseException:
        _restore(owner, reference, ciphertext)
        _restore_save_state(
            owner,
            primary_key=primary_key,
            adding=adding,
            database=database,
            loaded_signature=loaded_signature,
        )
        if intent is not None:
            queue_single_secret(
                owner,
                intent.payload,
                user=intent.user,
                request=intent.request,
            )
        raise


@sensitive_variables()
def delete_single_secret_owner(
    owner: Any, original: Callable, args: tuple, kwargs: dict[str, Any]
) -> tuple[int, dict[str, int]]:
    spec = spec_for(owner)
    reference = getattr(owner, spec.reference_field)
    ciphertext = getattr(owner, spec.encrypted_field)
    if reference is None and not _has_owned_assignments(owner):
        return original(owner, *args, **kwargs)
    if _database_alias(owner, kwargs) != "default":
        raise ValidationError(
            "OpenBao credential material requires the default database transaction owner."
        )
    try:
        with single_secret_material_transaction([owner]) as context:
            actor = _resolve_actor(None, owner)
            for assignment in _owned_assignments(context, owner):
                _require_scope(assignment, actor, "delete")
                assignment.delete()
            setattr(owner, spec.reference_field, None)
            setattr(owner, spec.encrypted_field, "")
            from netbox_proxbox.services.encryption_recovery import (
                mark_encrypted_fields_for_write,
            )

            mark_encrypted_fields_for_write(owner, spec.encrypted_field)
            original_save = getattr(type(owner).save, "_proxbox_single_original", None)
            if original_save is None:
                raise ValidationError("The credential owner writer is not installed.")
            _persist_material_fields(owner, original_save, spec)
            return original(owner, *args, **kwargs)
    except BaseException:
        _restore(owner, reference, ciphertext)
        raise


def _install_model_writer(model: type) -> None:
    if getattr(model.save, "_proxbox_openbao_single_writer", False):
        return
    original_save = model.save
    original_delete = model.delete

    @wraps(original_save)
    def save(instance: Any, *args: Any, **kwargs: Any) -> Any:
        return save_single_secret_owner(instance, original_save, args, kwargs)

    @wraps(original_delete)
    def delete(instance: Any, *args: Any, **kwargs: Any) -> Any:
        return delete_single_secret_owner(instance, original_delete, args, kwargs)

    save._proxbox_openbao_single_writer = True
    save._proxbox_single_original = original_save
    delete._proxbox_openbao_single_writer = True
    model.save = save
    model.delete = delete


def install_single_secret_material_writer() -> None:
    """Install model save/delete boundaries for all declared owner types."""
    from netbox_proxbox.models import (
        FastAPIEndpoint,
        FirecrackerHost,
        PBSEndpoint,
        PDMEndpoint,
    )

    for model in (FastAPIEndpoint, PBSEndpoint, PDMEndpoint, FirecrackerHost):
        _install_model_writer(model)
