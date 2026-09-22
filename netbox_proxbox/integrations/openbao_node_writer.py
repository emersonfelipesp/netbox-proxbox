"""Persist queued node SSH material through the provider transaction owner."""

from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from django.core.exceptions import ValidationError
from django.db import router
from django.views.decorators.debug import sensitive_variables

from .openbao_node_pending import SLOTS, PendingCredential, consume_credentials
from .openbao_node_transaction import (
    current_node_material_context,
    current_node_request_actor,
    node_material_transaction,
)


def install_node_material_writer() -> None:
    """Install after encryption guards so node persistence owns material."""
    from netbox_proxbox.models import NodeSSHCredential, ProxmoxNode

    original_save = NodeSSHCredential.save
    original_delete = NodeSSHCredential.delete
    if not getattr(original_save, "_proxbox_openbao_node_writer", False):

        @wraps(original_save)
        @sensitive_variables()
        def save(instance: Any, *args: Any, **kwargs: Any) -> Any:
            return save_node_credential(instance, original_save, args, kwargs)

        @wraps(original_delete)
        @sensitive_variables()
        def delete(instance: Any, *args: Any, **kwargs: Any) -> Any:
            return delete_node_credential(
                instance,
                original_save,
                original_delete,
                args,
                kwargs,
            )

        save._proxbox_openbao_node_writer = True
        delete._proxbox_openbao_node_writer = True
        NodeSSHCredential.save = save
        NodeSSHCredential.delete = delete
    original_node_save = ProxmoxNode.save
    if not getattr(original_node_save, "_proxbox_openbao_node_link_writer", False):

        @wraps(original_node_save)
        def save_node(instance: Any, *args: Any, **kwargs: Any) -> Any:
            return save_node_link(instance, original_node_save, args, kwargs)

        save_node._proxbox_openbao_node_link_writer = True
        ProxmoxNode.save = save_node


def _restore_references(owner: Any, references: dict[str, Any]) -> None:
    for name, value in references.items():
        setattr(owner, name, value)


def _database_alias(owner: Any, kwargs: dict[str, Any]) -> str:
    return kwargs.get("using") or router.db_for_write(type(owner), instance=owner)


@sensitive_variables()
def _requires_owner(
    owner: Any,
    pending: dict[str, PendingCredential],
    kwargs: dict[str, Any],
) -> bool:
    if pending or any(getattr(owner, name, None) for name in SLOTS):
        return True
    if owner.pk is None:
        return False
    watched = (*SLOTS, "auth_method", "node_id")
    update_fields = kwargs.get("update_fields")
    if update_fields is not None:
        return bool(set(update_fields).intersection(watched))
    previous = type(owner).objects.filter(pk=owner.pk).values(*watched).first()
    return previous is not None and any(
        getattr(owner, name) != previous[name] for name in watched
    )


@sensitive_variables()
def _validate_reference_mutations(
    context: Any,
    owner: Any,
    pending: dict[str, PendingCredential],
) -> None:
    previous = context.owners.get(owner.pk)
    direct = [
        name
        for name in SLOTS
        if name not in pending and getattr(owner, name) != getattr(previous, name, None)
    ]
    if direct:
        raise ValidationError(
            "OpenBao node credential UUID references cannot be rebound directly: "
            + ", ".join(direct)
            + ". Use the credential material setters or clear operation."
        )


@sensitive_variables()
def _validate_partial_assignment_state(
    context: Any,
    owner: Any,
    pending: dict[str, PendingCredential],
    kwargs: dict[str, Any],
) -> None:
    update_fields = kwargs.get("update_fields")
    if update_fields is None:
        return
    previous = context.owners.get(owner.pk)
    if previous is None:
        if pending:
            raise ValidationError(
                "OpenBao material cannot be created with a partial node save."
            )
        return
    included = _normalized_update_fields(update_fields)
    omitted = [
        name
        for name in ("auth_method", "node_id")
        if name not in included and getattr(owner, name) != getattr(previous, name)
    ]
    if omitted:
        raise ValidationError(
            "OpenBao node assignment selectors changed outside update_fields: "
            + ", ".join(omitted)
            + "."
        )


def _normalized_update_fields(update_fields: Any) -> set[str]:
    """Treat Django's relation name and attname as one node selector."""
    included = set(update_fields)
    if "node" in included:
        included.add("node_id")
    if "node_id" in included:
        included.add("node")
    return included


def _uses_openbao(owner: Any) -> bool:
    from .openbao import node_uses_openbao_storage

    return node_uses_openbao_storage(owner)


def _node_link_state(
    node: Any,
    kwargs: dict[str, Any],
) -> tuple[bool, bool, int | None]:
    if node.pk is None:
        return False, False, None
    previous_id = (
        type(node)
        .objects.filter(pk=node.pk)
        .values_list("netbox_device_id", flat=True)
        .first()
    )
    changed = node.netbox_device_id != previous_id
    update_fields = kwargs.get("update_fields")
    if update_fields is None:
        return changed, changed, previous_id
    included = bool({"netbox_device", "netbox_device_id"}.intersection(update_fields))
    return changed, included, previous_id


def _linked_openbao_owner(node: Any) -> Any | None:
    from netbox_proxbox.models import NodeSSHCredential

    owner = NodeSSHCredential.objects.filter(node_id=node.pk).first()
    if owner is None or not any(getattr(owner, name, None) for name in SLOTS):
        return None
    return owner if _uses_openbao(owner) else None


def _validate_node_link_write(
    node: Any,
    owner: Any,
    changed: bool,
    included: bool,
    kwargs: dict[str, Any],
) -> None:
    if owner is None:
        return
    if changed and not included:
        raise ValidationError(
            "The Proxmox node device link changed outside update_fields."
        )
    if _database_alias(node, kwargs) != "default":
        raise ValidationError(
            "OpenBao node assignments require the default database transaction owner."
        )


def _reconcile_node_link(
    context: Any,
    node: Any,
    owner: Any,
    original: Callable,
    args: tuple,
    kwargs: dict[str, Any],
) -> Any:
    from .openbao_assignments import resolve_transaction_actor
    from .openbao_node_assignments import reconcile_node_assignment

    result = original(node, *args, **kwargs)
    context.nodes[node.pk].netbox_device_id = node.netbox_device_id
    actor = resolve_transaction_actor(
        {},
        getattr(node, "_openbao_actor_user", None)
        or getattr(owner, "_openbao_actor_user", None),
    )
    reconcile_node_assignment(context, owner, actor=actor)
    return result


def save_node_link(
    node: Any,
    original: Callable,
    args: tuple,
    kwargs: dict[str, Any],
) -> Any:
    """Reconcile an existing OpenBao owner in the same transaction as its link."""
    changed, included, previous_id = _node_link_state(node, kwargs)
    if not changed and not included:
        return original(node, *args, **kwargs)
    owner = _linked_openbao_owner(node)
    if owner is None:
        return original(node, *args, **kwargs)
    _validate_node_link_write(node, owner, changed, included, kwargs)
    targets = {node.netbox_device_id} if node.netbox_device_id else set()
    with node_material_transaction([owner], target_device_ids=targets) as context:
        locked_node = context.nodes.get(node.pk)
        if locked_node is None or locked_node.netbox_device_id != previous_id:
            raise ValidationError(
                "The Proxmox node device link changed before ownership was acquired."
            )
        return _reconcile_node_link(context, node, owner, original, args, kwargs)


def _has_owned_assignments(owner: Any) -> bool:
    from django.contrib.contenttypes.models import ContentType

    from .openbao import is_netbox_openbao_installed

    if not is_netbox_openbao_installed():
        if any(getattr(owner, name, None) for name in SLOTS):
            raise ValidationError(
                "OpenBao node references remain, but netbox-openbao is unavailable. "
                "Restore the provider, remove assignments through the supported "
                "cleanup path, and clear the references before deleting or switching storage."
            )
        return False

    try:
        from netbox_openbao.models import Credential, CredentialAssignment
    except ImportError as exc:
        if any(getattr(owner, name, None) for name in SLOTS):
            raise ValidationError(
                "OpenBao node references remain, but netbox-openbao is unavailable. "
                "Restore the provider, remove assignments through the supported "
                "cleanup path, and clear the references before deleting or switching storage."
            ) from exc
        return False

    references = [getattr(owner, name, None) for name in SLOTS]
    credential_ids = Credential.objects.filter(uuid__in=references).values_list(
        "pk", flat=True
    )
    return CredentialAssignment.objects.filter(
        credential_id__in=credential_ids,
        assigned_object_type=ContentType.objects.get(app_label="dcim", model="device"),
        purpose="login",
        is_primary=True,
    ).exists()


@sensitive_variables()
def delete_node_credential(
    owner: Any,
    original_save: Callable,
    original_delete: Callable,
    args: tuple,
    kwargs: dict[str, Any],
) -> tuple[int, dict[str, int]]:
    """Unlink owned device assignments and delete the owner atomically."""
    references = {name: getattr(owner, name) for name in SLOTS}
    if not any(references.values()) and not _has_owned_assignments(owner):
        return original_delete(owner, *args, **kwargs)
    if _database_alias(owner, kwargs) != "default":
        raise ValidationError(
            "OpenBao node material requires the default database transaction owner."
        )
    try:
        with node_material_transaction([owner]) as context:
            from .openbao_assignments import fresh_material_actor
            from .openbao_node_assignments import remove_node_assignments

            actor = fresh_material_actor(
                getattr(owner, "_openbao_actor_user", None)
                or current_node_request_actor()
            )
            remove_node_assignments(context, owner, actor=actor)
            for name in SLOTS:
                setattr(owner, name, None)
            original_save(owner, update_fields=list(SLOTS), using="default")
            return original_delete(owner, *args, **kwargs)
    except BaseException:
        _restore_references(owner, references)
        raise


@sensitive_variables()
def save_node_credential(
    owner: Any,
    original: Callable,
    args: tuple,
    kwargs: dict[str, Any],
) -> Any:
    pending = consume_credentials(owner)
    references = {name: getattr(owner, name) for name in SLOTS}
    if not _uses_openbao(owner):
        return _save_legacy(owner, pending, references, original, args, kwargs)
    if (
        not _requires_owner(owner, pending, kwargs)
        and current_node_material_context() is None
    ):
        return original(owner, *args, **kwargs)
    if _database_alias(owner, kwargs) != "default":
        raise ValidationError(
            "OpenBao node material requires the default database transaction owner."
        )
    try:
        new_node_ids = {owner.node_id} if owner.pk is None else set()
        with node_material_transaction(
            [owner],
            allow_new=owner.pk is None,
            new_node_ids=new_node_ids,
        ) as context:
            return _save_owned(context, owner, pending, original, args, kwargs)
    except BaseException:
        _restore_references(owner, references)
        raise


@sensitive_variables()
def _save_legacy(
    owner: Any,
    pending: dict[str, PendingCredential],
    references: dict[str, Any],
    original: Callable,
    args: tuple,
    kwargs: dict[str, Any],
) -> Any:
    if pending:
        raise ValidationError(
            "The node credential storage selection changed after material was supplied."
        )
    if any(references.values()) or _has_owned_assignments(owner):
        raise ValidationError(
            "OpenBao node references or assignments remain. Restore OpenBao, "
            "clean them up explicitly, and only then select legacy storage."
        )
    return original(owner, *args, **kwargs)


@sensitive_variables()
def _save_owned(
    context: Any,
    owner: Any,
    pending: dict[str, PendingCredential],
    original: Callable,
    args: tuple,
    kwargs: dict[str, Any],
) -> Any:
    from .openbao_assignments import resolve_transaction_actor
    from .openbao_node_assignments import (
        apply_node_material,
        reconcile_node_assignment,
    )

    context.admit(owner)
    _validate_reference_mutations(context, owner, pending)
    _validate_partial_assignment_state(context, owner, pending, kwargs)
    actor = resolve_transaction_actor(
        pending,
        getattr(owner, "_openbao_actor_user", None),
    )
    result = original(owner, *args, **kwargs)
    if pending:
        apply_node_material(context, owner, pending, actor=actor)
        original(owner, update_fields=list(pending), using="default")
    reconcile_node_assignment(context, owner, actor=actor)
    return result
