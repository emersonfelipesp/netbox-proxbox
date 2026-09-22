"""Persist queued endpoint material through the provider transaction owner."""

from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from django.core.exceptions import ValidationError
from django.db import router
from django.views.decorators.debug import sensitive_variables

from .openbao_pending import SLOTS, PendingCredential, consume_credentials
from .openbao_transaction import (
    current_endpoint_material_context,
    endpoint_material_transaction,
)


def install_endpoint_material_writer() -> None:
    """Install after encryption guards so endpoint persistence owns material."""
    from netbox_proxbox.models import ProxmoxEndpoint

    original = ProxmoxEndpoint.save
    if getattr(original, "_proxbox_openbao_writer", False):
        return

    @wraps(original)
    @sensitive_variables()
    def save(instance: Any, *args: Any, **kwargs: Any) -> Any:
        return save_endpoint(instance, original, args, kwargs)

    save._proxbox_openbao_writer = True
    ProxmoxEndpoint.save = save


def _restore_references(endpoint: Any, references: dict[str, Any]) -> None:
    for name, value in references.items():
        setattr(endpoint, name, value)


def _database_alias(endpoint: Any, kwargs: dict[str, Any]) -> str:
    return kwargs.get("using") or router.db_for_write(type(endpoint), instance=endpoint)


def _requires_owner(
    endpoint: Any,
    pending: dict[str, PendingCredential],
    kwargs: dict[str, Any],
) -> bool:
    if pending:
        return True
    if endpoint.pk is None:
        return False
    watched = (*SLOTS, "ssh_auth_method", "ssh_credential_source")
    update_fields = kwargs.get("update_fields")
    if update_fields is not None:
        return bool(set(update_fields).intersection(watched))
    previous = type(endpoint).objects.filter(pk=endpoint.pk).values(*watched).first()
    return previous is not None and any(
        getattr(endpoint, name) != previous[name] for name in watched
    )


def _validate_reference_mutations(
    context: Any,
    endpoint: Any,
    pending: dict[str, PendingCredential],
) -> None:
    previous = context.endpoints.get(endpoint.pk)
    if previous is None:
        return
    direct = [
        name
        for name in SLOTS
        if name not in pending and getattr(endpoint, name) != getattr(previous, name)
    ]
    if direct:
        raise ValidationError(
            "OpenBao credential UUID references cannot be rebound directly: "
            + ", ".join(direct)
            + ". Use the credential material setters or clear operation."
        )


def _validate_partial_assignment_state(
    context: Any,
    endpoint: Any,
    pending: dict[str, PendingCredential],
    kwargs: dict[str, Any],
) -> None:
    update_fields = kwargs.get("update_fields")
    if update_fields is None:
        return
    previous = context.endpoints.get(endpoint.pk)
    if previous is None:
        if pending:
            raise ValidationError(
                "OpenBao material cannot be created with a partial endpoint save."
            )
        return
    included = set(update_fields)
    selectors = ("ssh_auth_method", "ssh_credential_source")
    omitted_changes = [
        name
        for name in selectors
        if name not in included and getattr(endpoint, name) != getattr(previous, name)
    ]
    if omitted_changes:
        raise ValidationError(
            "OpenBao assignment selectors changed outside update_fields: "
            + ", ".join(omitted_changes)
            + "."
        )


@sensitive_variables()
def delete_endpoint(
    endpoint: Any,
    original: Callable,
    args: tuple,
    kwargs: dict[str, Any],
) -> tuple[int, dict[str, int]]:
    """Unlink owned assignments and delete the endpoint in one transaction."""
    from .openbao import endpoint_uses_openbao_storage

    from netbox_openbao.models import CredentialAssignment

    references = {name: getattr(endpoint, name) for name in SLOTS}
    has_assignments = CredentialAssignment.objects.filter(
        assigned_object_type__app_label=endpoint._meta.app_label,
        assigned_object_type__model=endpoint._meta.model_name,
        assigned_object_id=endpoint.pk,
    ).exists()
    if not endpoint_uses_openbao_storage(endpoint) or not (
        any(references.values()) or has_assignments
    ):
        return original(*args, **kwargs)
    if _database_alias(endpoint, kwargs) != "default":
        raise ValidationError(
            "OpenBao endpoint material requires the default database transaction owner."
        )
    try:
        with endpoint_material_transaction([endpoint]) as context:
            context.admit(endpoint)
            endpoint.purge_openbao_credentials()
            endpoint.save(update_fields=list(SLOTS), using="default")
            from .openbao_assignments import (
                fresh_material_actor,
                remove_endpoint_assignments,
            )

            actor = fresh_material_actor(getattr(endpoint, "_openbao_actor_user", None))
            remove_endpoint_assignments(context, endpoint, actor=actor)
            return original(*args, **kwargs)
    except BaseException:
        _restore_references(endpoint, references)
        raise


@sensitive_variables()
def save_endpoint(
    endpoint: Any,
    original: Callable,
    args: tuple,
    kwargs: dict[str, Any],
) -> Any:
    from .openbao import endpoint_uses_openbao_storage

    pending = consume_credentials(endpoint)
    references = {name: getattr(endpoint, name) for name in SLOTS}
    if not endpoint_uses_openbao_storage(endpoint):
        if pending:
            raise ValidationError(
                "The endpoint storage selection changed after material was supplied."
            )
        return original(endpoint, *args, **kwargs)
    if (
        not _requires_owner(endpoint, pending, kwargs)
        and current_endpoint_material_context() is None
    ):
        return original(endpoint, *args, **kwargs)
    if _database_alias(endpoint, kwargs) != "default":
        raise ValidationError(
            "OpenBao endpoint material requires the default database transaction owner."
        )
    try:
        with endpoint_material_transaction(
            [endpoint], allow_new=endpoint.pk is None
        ) as context:
            return _save_owned(context, endpoint, pending, original, args, kwargs)
    except BaseException:
        _restore_references(endpoint, references)
        raise


@sensitive_variables()
def _save_owned(
    context: Any,
    endpoint: Any,
    pending: dict[str, PendingCredential],
    original: Callable,
    args: tuple,
    kwargs: dict[str, Any],
) -> Any:
    from .openbao_assignments import (
        apply_endpoint_material,
        reconcile_endpoint_assignments,
        resolve_transaction_actor,
    )

    context.admit(endpoint)
    _validate_reference_mutations(context, endpoint, pending)
    _validate_partial_assignment_state(context, endpoint, pending, kwargs)
    actor = resolve_transaction_actor(
        pending,
        getattr(endpoint, "_openbao_actor_user", None),
    )
    result = original(endpoint, *args, **kwargs)
    if pending:
        apply_endpoint_material(context, endpoint, pending, actor=actor)
        original(endpoint, update_fields=list(pending), using="default")
    reconcile_endpoint_assignments(
        context,
        endpoint,
        actor=actor,
    )
    return result
