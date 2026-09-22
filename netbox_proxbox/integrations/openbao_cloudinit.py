"""OpenBao material boundary for VM cloud-init login credentials."""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import wraps
from typing import Any, Callable

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import router, transaction
from django.views.decorators.debug import sensitive_variables

from netbox_proxbox.choices import CredentialStorageBackendChoices
from netbox_proxbox.integrations.openbao_single_pending import PendingSingleSecret


@dataclass(frozen=True, slots=True)
class CloudInitSecretSpec:
    """One cloud-init login material type and its durable UUID field."""

    name: str
    reference_field: str
    material_field: str
    credential_type: str
    label: str


SPECS = {
    "password": CloudInitSecretSpec(
        "password",
        "openbao_password_credential_uuid",
        "password",
        "password",
        "VM login password",
    ),
    "private_key": CloudInitSecretSpec(
        "private_key",
        "openbao_keypair_credential_uuid",
        "private_key",
        "ssh-keypair",
        "VM login SSH keypair",
    ),
}
_PENDING_ATTRIBUTE = "_proxbox_openbao_cloudinit_pending"


@dataclass(frozen=True)
class PendingCloudInitSecret:
    """Reference-bound provider write intent with hidden material."""

    expected_uuid: Any
    payload: dict[str, str] | None = field(repr=False)
    user: Any = field(default=None, repr=False)
    request: Any = field(default=None, repr=False)


@dataclass
class CloudInitMaterialContext:
    """Prelocked owner, VM, assignment, credential, and policy graph."""

    owners: dict[int, Any]
    virtual_machines: dict[int, Any]
    assignments: dict[int, list[Any]]
    credentials: dict[str, Any]
    policy: Any
    content_type: Any
    allow_new: bool = False
    new_instances: dict[int, Any] = field(default_factory=dict, repr=False)

    def admit(self, owner: Any) -> None:
        """Require an existing owner or a predeclared new owner's VM."""
        if self.new_instances.get(id(owner)) is owner:
            return
        vm_id = getattr(owner, "virtual_machine_id", None)
        if owner.pk is not None and self.owners.get(int(owner.pk)) is not None:
            return
        if self.allow_new and vm_id in self.virtual_machines:
            self.new_instances[id(owner)] = owner
            return
        raise ValidationError(
            "Cloud-init credential ownership was not declared before material access."
        )


_CURRENT: ContextVar[CloudInitMaterialContext | None] = ContextVar(
    "proxbox_cloudinit_material_context", default=None
)


def cloudinit_uses_openbao_storage() -> bool:
    """Return the effective plugin-wide cloud-init credential backend."""
    from .openbao import effective_credential_storage_backend

    return (
        effective_credential_storage_backend()
        == CredentialStorageBackendChoices.OPENBAO
    )


def _spec(name: str) -> CloudInitSecretSpec:
    try:
        return SPECS[name]
    except KeyError as exc:
        raise ValueError("Unsupported cloud-init credential material.") from exc


@sensitive_variables()
def _pending(owner: Any) -> dict[str, PendingCloudInitSecret]:
    return getattr(owner, _PENDING_ATTRIBUTE, {})


@sensitive_variables()
def _replace_pending(owner: Any, intents: dict[str, PendingCloudInitSecret]) -> None:
    if intents:
        setattr(owner, _PENDING_ATTRIBUTE, intents)
        return
    owner.__dict__.pop(_PENDING_ATTRIBUTE, None)


@sensitive_variables()
def queue_cloudinit_secret(
    owner: Any,
    name: str,
    value: object | None,
    *,
    user: Any = None,
    request: Any = None,
) -> None:
    """Queue an explicit OpenBao write or cleanup for one login material type."""
    if not cloudinit_uses_openbao_storage():
        raise ValidationError(
            "Cloud-init password and private-key material require OpenBao storage. "
            "Legacy storage preserves credential_reference_id unchanged."
        )
    from .openbao import validate_openbao_storage_available

    validate_openbao_storage_available(storage_backend="openbao")
    spec = _spec(name)
    intents = dict(_pending(owner))
    previous = intents.get(name)
    expected = (
        previous.expected_uuid
        if previous is not None
        else getattr(owner, spec.reference_field, None)
    )
    payload = None if value in (None, "") else {spec.material_field: str(value)}
    intents[name] = PendingCloudInitSecret(expected, payload, user, request)
    _replace_pending(owner, intents)


@sensitive_variables()
def _take_pending(owner: Any) -> dict[str, PendingCloudInitSecret]:
    return owner.__dict__.pop(_PENDING_ATTRIBUTE, {})


@sensitive_variables()
def cloudinit_secret_configured(owner: Any, name: str) -> bool:
    """Return configured state without resolving provider material."""
    spec = _spec(name)
    intent = _pending(owner).get(name)
    if intent is not None:
        return intent.payload is not None
    if cloudinit_uses_openbao_storage():
        return getattr(owner, spec.reference_field, None) is not None
    return getattr(owner, "credential_reference_id", None) is not None


def _credential(reference: Any, spec: CloudInitSecretSpec) -> Any:
    from .openbao import _credential_for_uuid

    selected = _credential_for_uuid(reference)
    if selected is None:
        raise ValidationError(
            f"The selected OpenBao {spec.label} reference cannot be resolved."
        )
    if selected.credential_type != spec.credential_type:
        raise ValidationError(
            f"The selected OpenBao {spec.label} has an incompatible type."
        )
    return selected


@sensitive_variables()
def resolve_cloudinit_secret(owner: Any, name: str, *, user: Any = None) -> str:
    """Resolve OpenBao material and never consult the legacy opaque reference."""
    if not cloudinit_uses_openbao_storage():
        raise ValidationError(
            "Cloud-init credential material is external in legacy storage mode."
        )
    spec = _spec(name)
    intent = _pending(owner).get(name)
    if intent is not None and intent.payload is not None:
        return intent.payload[spec.material_field]
    reference = getattr(owner, spec.reference_field, None)
    if reference is None:
        raise ValidationError(f"The selected OpenBao {spec.label} is not configured.")
    from .openbao import reveal_credential_material
    from .openbao_single_transaction import current_single_secret_actor

    material = reveal_credential_material(
        _credential(reference, spec), user=user or current_single_secret_actor()
    )
    value = material.get(spec.material_field)
    if value in (None, ""):
        raise ValidationError(
            f"The selected OpenBao {spec.label} material is unavailable."
        )
    return str(value)


def cloudinit_assignment_lookup(owner: Any) -> dict[str, str] | None:
    """Return Ansible-compatible selectors for the parent VM login assignment."""
    vm_id = getattr(owner, "virtual_machine_id", None)
    if vm_id is None:
        return None
    return {
        "assigned_object_type": "virtualization.virtualmachine",
        "assigned_object_id": str(vm_id),
        "purpose": "login",
    }


@sensitive_variables()
def _references(owner: Any) -> dict[str, Any]:
    return {
        name: getattr(owner, spec.reference_field, None) for name, spec in SPECS.items()
    }


def _expected_primary_name(owner: Any, references: dict[str, Any]) -> str | None:
    if owner.ssh_pwauth is True and references["password"] is not None:
        return "password"
    if references["private_key"] is not None:
        return "private_key"
    if references["password"] is not None:
        return "password"
    return None


def _assignment_rows(owner: Any, references: dict[str, Any]) -> Any | None:
    try:
        from netbox_openbao.models import CredentialAssignment
    except ImportError:
        return None
    return CredentialAssignment.objects.filter(
        credential__uuid__in=[value for value in references.values() if value],
        assigned_object_type__app_label="virtualization",
        assigned_object_type__model="virtualmachine",
        assigned_object_id=owner.virtual_machine_id,
        purpose="login",
        enabled=True,
    )


def _assignment_references(rows: Any) -> set[str]:
    return {str(row.credential.uuid) for row in rows}


def _primary_assignment_ready(
    owner: Any, references: dict[str, Any], rows: Any
) -> bool:
    primary_name = _expected_primary_name(owner, references)
    primary_uuid = references.get(primary_name) if primary_name else None
    return rows.filter(is_primary=True, credential__uuid=primary_uuid).count() == 1


def cloudinit_assignment_readiness(owner: Any) -> tuple[bool, str]:
    """Check the complete login assignment shape without revealing material."""
    if not cloudinit_uses_openbao_storage():
        return True, "Legacy storage uses the external credential reference."
    references = _references(owner)
    if not any(references.values()):
        return False, "No OpenBao cloud-init login credential is configured."
    lookup = cloudinit_assignment_lookup(owner)
    if lookup is None:
        return False, "Persist the cloud-init owner before checking readiness."
    rows = _assignment_rows(owner, references)
    if rows is None:
        return False, "The credential provider is unavailable; restore it before use."
    expected = {str(value) for value in references.values() if value}
    if _assignment_references(rows) != expected:
        return False, "The selected provider credential assignments are not ready."
    if not _primary_assignment_ready(owner, references, rows):
        return False, "The selected provider primary login assignment is not ready."
    return True, "The selected provider credential assignments are ready."


@sensitive_variables()
def _owner_snapshot(owner: Any) -> tuple[Any, Any, tuple[Any, ...]]:
    references = tuple(
        getattr(owner, spec.reference_field, None) for spec in SPECS.values()
    )
    return (
        getattr(owner, "virtual_machine_id", None),
        getattr(owner, "ssh_pwauth", None),
        references,
    )


@sensitive_variables()
def _validate_locked_owner(observed: Any, durable: Any) -> None:
    if _owner_snapshot(observed) != _owner_snapshot(durable):
        raise ValidationError(
            "The cloud-init credential owner changed before ownership was acquired."
        )


@sensitive_variables()
def _lock_owners(owners: Sequence[Any]) -> dict[int, Any]:
    from netbox_proxbox.models import ProxmoxVMCloudInit

    observed = {int(owner.pk): owner for owner in owners if owner.pk is not None}
    locked = {
        int(owner.pk): owner
        for owner in ProxmoxVMCloudInit.objects.select_for_update()
        .filter(pk__in=observed)
        .order_by("pk")
    }
    if len(locked) != len(observed):
        raise ValidationError(
            "A declared cloud-init credential owner no longer exists."
        )
    for owner_id, snapshot in observed.items():
        _validate_locked_owner(snapshot, locked[owner_id])
    return locked


def _lock_virtual_machines(ids: set[int]) -> dict[int, Any]:
    from virtualization.models import VirtualMachine

    locked = {
        int(vm.pk): vm
        for vm in VirtualMachine.objects.select_for_update()
        .filter(pk__in=ids)
        .order_by("pk")
    }
    if len(locked) != len(ids):
        raise ValidationError("A declared cloud-init virtual machine no longer exists.")
    return locked


def _lock_assignments(vm_ids: set[int], content_type: Any) -> dict[int, list[Any]]:
    from netbox_openbao.models import CredentialAssignment

    result = {vm_id: [] for vm_id in vm_ids}
    rows = (
        CredentialAssignment.objects.select_for_update()
        .filter(
            assigned_object_type=content_type,
            assigned_object_id__in=vm_ids,
            purpose="login",
        )
        .order_by("pk")
    )
    for row in rows:
        result[int(row.assigned_object_id)].append(row)
    return result


@sensitive_variables()
def _reference_values(owners: Sequence[Any]) -> set[str]:
    return {
        str(value)
        for owner in owners
        for value in _references(owner).values()
        if value is not None
    }


@sensitive_variables()
def _lock_credentials(
    owners: Sequence[Any], assignments: dict[int, list[Any]]
) -> dict[str, Any]:
    from django.db.models import Q
    from netbox_openbao.models import Credential

    references = _reference_values(owners)
    assigned_ids = {row.credential_id for rows in assignments.values() for row in rows}
    subjects = list(
        Credential.objects.filter(Q(uuid__in=references) | Q(pk__in=assigned_ids))
    )
    found = {str(row.uuid) for row in subjects}
    found_ids = {row.pk for row in subjects}
    if not references.issubset(found):
        raise ValidationError("An existing cloud-init credential cannot be resolved.")
    if not assigned_ids.issubset(found_ids):
        raise ValidationError("An assigned cloud-init credential no longer exists.")
    return {str(row.uuid): row for row in subjects}


@sensitive_variables()
def _declare_context(
    owners: Sequence[Any], vm_ids: set[int], *, allow_new: bool
) -> CloudInitMaterialContext:
    from django.contrib.contenttypes.models import ContentType
    from virtualization.models import VirtualMachine

    from .openbao import _default_policy
    from .openbao_single_transaction import _locked_settings

    _locked_settings()
    locked_owners = _lock_owners(owners)
    all_vm_ids = vm_ids | {
        int(owner.virtual_machine_id) for owner in locked_owners.values()
    }
    virtual_machines = _lock_virtual_machines(all_vm_ids)
    content_type = ContentType.objects.get_for_model(VirtualMachine)
    assignments = _lock_assignments(all_vm_ids, content_type)
    credentials = _lock_credentials(list(locked_owners.values()), assignments)
    policy = _default_policy()
    policy_identity = (policy.pk, policy.engine_id)
    from netbox_openbao.synchronization import lock_material_subjects

    locked = lock_material_subjects(
        credentials.values(), additional_policy_ids={policy.pk}
    )
    policy = _default_policy()
    if (policy.pk, policy.engine_id) != policy_identity:
        raise ValidationError(
            "The default OpenBao policy changed during ownership acquisition."
        )
    return CloudInitMaterialContext(
        owners=locked_owners,
        virtual_machines=virtual_machines,
        assignments=assignments,
        credentials={str(row.uuid): row for row in locked.values()},
        policy=policy,
        content_type=content_type,
        allow_new=allow_new,
    )


@contextmanager
@sensitive_variables()
def cloudinit_material_transaction(
    owners: Sequence[Any], vm_ids: set[int], *, allow_new: bool = False
) -> Iterator[CloudInitMaterialContext]:
    """Begin provider compensation before the framework database transaction."""
    existing = _CURRENT.get()
    if existing is not None:
        for owner in owners:
            existing.admit(owner)
        yield existing
        return
    if transaction.get_connection("default").in_atomic_block:
        raise ValidationError(
            "OpenBao cloud-init material requires its provider transaction before "
            "the NetBox database transaction. Use the supported UI or API boundary."
        )
    from .openbao_single_transaction import _material_transaction_factory

    with _material_transaction_factory()():
        context = _declare_context(owners, vm_ids, allow_new=allow_new)
        for owner in owners:
            context.admit(owner)
        token = _CURRENT.set(context)
        try:
            yield context
        finally:
            _CURRENT.reset(token)


@sensitive_variables()
def _request_vm_ids(payloads: Sequence[Mapping[str, Any]]) -> set[int]:
    from .openbao_node_request import request_pk

    return {
        vm_id
        for payload in payloads
        if (vm_id := request_pk(payload.get("virtual_machine"))) is not None
    }


@sensitive_variables()
def _payload_has_material(payloads: Sequence[Mapping[str, Any]]) -> bool:
    return any(any(name in payload for name in SPECS) for payload in payloads)


@sensitive_variables()
def _owner_has_state(owner: Any) -> bool:
    return any(_references(owner).values()) or _has_owned_assignments(owner)


@contextmanager
@sensitive_variables()
def cloudinit_mutation_boundary(
    owners: Sequence[Any],
    payloads: Sequence[Mapping[str, Any]],
    *,
    actor: Any,
    request: Any = None,
    allow_new: bool = False,
) -> Iterator[None]:
    """Own compensation and actor state for one complete API mutation."""
    from .openbao_single_request import mark_single_secret_request_sensitive
    from .openbao_single_transaction import single_secret_actor_scope

    if request is not None:
        mark_single_secret_request_sensitive(request)
    requires = any(_owner_has_state(owner) for owner in owners)
    requires = requires or (
        cloudinit_uses_openbao_storage() and _payload_has_material(payloads)
    )
    if not requires:
        with single_secret_actor_scope(actor, request):
            yield
        return
    vm_ids = _request_vm_ids(payloads) | {
        int(owner.virtual_machine_id) for owner in owners
    }
    with single_secret_actor_scope(actor, request):
        with cloudinit_material_transaction(owners, vm_ids, allow_new=allow_new):
            yield


@sensitive_variables()
def _restore_pending(owner: Any, intents: dict[str, PendingCloudInitSecret]) -> None:
    current = dict(_pending(owner))
    current.update(intents)
    _replace_pending(owner, current)


def _new_credential(
    context: CloudInitMaterialContext, owner: Any, spec: CloudInitSecretSpec
) -> Any:
    from netbox_openbao.models import Credential

    return Credential(
        name=f"Proxbox {owner.virtual_machine} — {spec.label}",
        credential_type=spec.credential_type,
        policy=context.policy,
        engine=context.policy.engine,
    )


@sensitive_variables()
def _actor(intent: PendingCloudInitSecret | None, owner: Any) -> Any:
    from .openbao_single_transaction import current_single_secret_actor
    from .openbao_single_writer import _fresh_actor

    candidate = intent.user if intent is not None else None
    return _fresh_actor(candidate or current_single_secret_actor())


@sensitive_variables()
def _apply_intent(
    context: CloudInitMaterialContext,
    owner: Any,
    spec: CloudInitSecretSpec,
    intent: PendingCloudInitSecret,
    durable_reference: Any,
) -> None:
    from .openbao_single_writer import _write_material

    current = getattr(owner, spec.reference_field, None)
    if current != durable_reference or intent.expected_uuid != durable_reference:
        raise ValidationError(
            "The cloud-init credential reference changed before persistence."
        )
    if intent.payload is None:
        setattr(owner, spec.reference_field, None)
        return
    credential = context.credentials.get(str(current)) if current else None
    if credential is not None and credential.credential_type != spec.credential_type:
        raise ValidationError("The cloud-init credential type is incompatible.")
    credential = credential or _new_credential(context, owner, spec)
    pending = PendingSingleSecret(
        intent.expected_uuid,
        intent.payload,
        intent.user,
        intent.request,
    )
    stored = _write_material(credential, pending, actor=_actor(intent, owner))
    context.credentials[str(stored.uuid)] = stored
    setattr(owner, spec.reference_field, stored.uuid)


def _save_assignment(assignment: Any, actor: Any, *, creating: bool) -> None:
    from .openbao_single_writer import _require_scope

    if creating and not actor.has_perm("netbox_openbao.add_credentialassignment"):
        raise PermissionDenied(
            "Creating a credential assignment requires add permission."
        )
    if not creating:
        _require_scope(assignment, actor, "change")
    assignment.full_clean()
    assignment.save()


def _remove_retired_assignments(
    rows: list[Any], retained_ids: set[int], owned_ids: set[int], actor: Any
) -> None:
    from .openbao_single_writer import _require_scope

    for assignment in list(rows):
        if assignment.credential_id not in owned_ids - retained_ids:
            continue
        _require_scope(assignment, actor, "delete")
        assignment.delete()
        rows.remove(assignment)


def _assignment_for(rows: list[Any], credential_id: int) -> Any | None:
    return next((row for row in rows if row.credential_id == credential_id), None)


def _credential_ids(
    context: CloudInitMaterialContext, references: dict[str, Any]
) -> set[int]:
    return {
        context.credentials[str(value)].pk for value in references.values() if value
    }


def _remove_previous_vm_assignments(
    context: CloudInitMaterialContext,
    owner: Any,
    previous_vm_id: int,
    previous_ids: set[int],
    actor: Any,
) -> None:
    if previous_vm_id == owner.virtual_machine_id:
        return
    old_rows = context.assignments.setdefault(previous_vm_id, [])
    _remove_retired_assignments(old_rows, set(), previous_ids, actor)


def _desired_primary_id(
    context: CloudInitMaterialContext,
    owner: Any,
    references: dict[str, Any],
) -> int | None:
    name = _expected_primary_name(owner, references)
    reference = references.get(name) if name else None
    return context.credentials[str(reference)].pk if reference else None


def _refuse_foreign_primary(
    rows: list[Any], retained_ids: set[int], desired_primary_id: int | None
) -> None:
    foreign = next(
        (
            row
            for row in rows
            if row.is_primary and row.credential_id not in retained_ids
        ),
        None,
    )
    if desired_primary_id is not None and foreign is not None:
        raise ValidationError(
            "A foreign primary login assignment already exists for this virtual machine."
        )


def _demote_owned_primaries(
    rows: list[Any], retained_ids: set[int], desired_primary_id: int | None, actor: Any
) -> None:
    for row in rows:
        if row.credential_id not in retained_ids or not row.is_primary:
            continue
        if row.credential_id == desired_primary_id:
            continue
        row.is_primary = False
        _save_assignment(row, actor, creating=False)


def _new_assignment(
    context: CloudInitMaterialContext, owner: Any, credential_id: int
) -> Any:
    from netbox_openbao.models import CredentialAssignment

    return CredentialAssignment(
        credential_id=credential_id,
        assigned_object_type=context.content_type,
        assigned_object_id=owner.virtual_machine_id,
        purpose="login",
        enabled=True,
    )


def _ensure_assignment_row(
    context: CloudInitMaterialContext,
    owner: Any,
    rows: list[Any],
    credential_id: int,
    desired_primary_id: int | None,
    actor: Any,
) -> None:
    row = _assignment_for(rows, credential_id)
    creating = row is None
    if creating:
        row = _new_assignment(context, owner, credential_id)
    if not row.enabled:
        raise ValidationError(
            "A disabled login assignment cannot be enabled implicitly."
        )
    should_be_primary = credential_id == desired_primary_id
    if creating or row.is_primary != should_be_primary:
        row.is_primary = should_be_primary
        _save_assignment(row, actor, creating=creating)
    if creating:
        rows.append(row)


def _ensure_assignments(
    context: CloudInitMaterialContext,
    owner: Any,
    previous_references: dict[str, Any],
    previous_vm_id: int,
    actor: Any,
) -> None:
    references = _references(owner)
    retained = _credential_ids(context, references)
    previous = _credential_ids(context, previous_references)
    _remove_previous_vm_assignments(context, owner, previous_vm_id, previous, actor)
    rows = context.assignments.setdefault(int(owner.virtual_machine_id), [])
    _remove_retired_assignments(rows, retained, previous, actor)
    desired = _desired_primary_id(context, owner, references)
    _refuse_foreign_primary(rows, retained, desired)
    _demote_owned_primaries(rows, retained, desired, actor)
    for credential_id in sorted(retained):
        _ensure_assignment_row(context, owner, rows, credential_id, desired, actor)


def _validate_references(owner: Any, previous: Any) -> None:
    for spec in SPECS.values():
        if getattr(owner, spec.reference_field) != getattr(
            previous, spec.reference_field
        ):
            raise ValidationError(
                "OpenBao cloud-init UUID references cannot be rebound directly."
            )


def _has_owned_assignments(owner: Any) -> bool:
    if owner.pk is None or owner.virtual_machine_id is None:
        return False
    references = [value for value in _references(owner).values() if value]
    if not references:
        return False
    from .openbao import is_netbox_openbao_installed

    if not is_netbox_openbao_installed():
        raise ValidationError(
            "OpenBao cloud-init references remain, but netbox-openbao is unavailable."
        )
    try:
        from netbox_openbao.models import CredentialAssignment
    except ImportError as exc:
        raise ValidationError(
            "OpenBao cloud-init references remain, but netbox-openbao is "
            "unavailable. Restore the provider and use the supported cleanup path."
        ) from exc

    return CredentialAssignment.objects.filter(
        credential__uuid__in=references,
        assigned_object_type__app_label="virtualization",
        assigned_object_type__model="virtualmachine",
        assigned_object_id=owner.virtual_machine_id,
        purpose="login",
    ).exists()


def _persist_reference_fields(owner: Any, original: Callable) -> None:
    original(
        owner,
        update_fields=tuple(spec.reference_field for spec in SPECS.values()),
        using="default",
    )


@sensitive_variables()
def _save_legacy_cloudinit(
    owner: Any,
    original: Callable,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    intents: dict[str, PendingCloudInitSecret],
    references: dict[str, Any],
) -> Any:
    if intents:
        _restore_pending(owner, intents)
        raise ValidationError(
            "Cloud-init material cannot be written while legacy storage is selected."
        )
    if any(references.values()) or _has_owned_assignments(owner):
        raise ValidationError(
            "OpenBao cloud-init references remain. Restore OpenBao and clean them "
            "before switching storage backends."
        )
    return original(owner, *args, **kwargs)


@sensitive_variables()
def _save_with_context(
    context: CloudInitMaterialContext,
    owner: Any,
    original: Callable,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    intents: dict[str, PendingCloudInitSecret],
    references: dict[str, Any],
) -> Any:
    context.admit(owner)
    previous = context.owners.get(int(owner.pk)) if owner.pk is not None else None
    if previous is not None:
        _validate_references(owner, previous)
        references = _references(previous)
    previous_vm_id = int(
        previous.virtual_machine_id
        if previous is not None
        else owner.virtual_machine_id
    )
    result = original(owner, *args, **kwargs)
    for name, intent in intents.items():
        _apply_intent(
            context,
            owner,
            _spec(name),
            intent,
            references.get(name),
        )
    if intents:
        _persist_reference_fields(owner, original)
    actor = _actor(next(iter(intents.values()), None), owner)
    _ensure_assignments(context, owner, references, previous_vm_id, actor)
    return result


@sensitive_variables()
def _restore_owner_state(
    owner: Any,
    references: dict[str, Any],
    intents: dict[str, PendingCloudInitSecret],
    state: tuple[Any, bool, Any],
) -> None:
    for name, value in references.items():
        setattr(owner, _spec(name).reference_field, value)
    owner.pk, owner._state.adding, owner._state.db = state
    _restore_pending(owner, intents)


def _require_default_database(owner: Any, kwargs: dict[str, Any]) -> None:
    selected = kwargs.get("using") or router.db_for_write(type(owner), instance=owner)
    if selected != "default":
        raise ValidationError(
            "OpenBao cloud-init material requires the default database."
        )


@sensitive_variables()
def save_cloudinit_owner(
    owner: Any, original: Callable, args: tuple[Any, ...], kwargs: dict[str, Any]
) -> Any:
    intents = _take_pending(owner)
    before = _references(owner)
    if not cloudinit_uses_openbao_storage():
        return _save_legacy_cloudinit(owner, original, args, kwargs, intents, before)
    needs_provider = bool(
        intents or any(before.values()) or _has_owned_assignments(owner)
    )
    if not needs_provider:
        return original(owner, *args, **kwargs)
    _require_default_database(owner, kwargs)
    state = owner.pk, owner._state.adding, owner._state.db
    try:
        vm_ids = {int(owner.virtual_machine_id)}
        with cloudinit_material_transaction(
            [owner] if owner.pk else [], vm_ids, allow_new=owner.pk is None
        ) as context:
            return _save_with_context(
                context, owner, original, args, kwargs, intents, before
            )
    except BaseException:
        _restore_owner_state(owner, before, intents, state)
        raise


def _restore_reference_fields(owner: Any, references: dict[str, Any]) -> None:
    for name, value in references.items():
        setattr(owner, _spec(name).reference_field, value)


def _delete_with_context(
    owner: Any,
    original: Callable,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    before: dict[str, Any],
) -> Any:
    with cloudinit_material_transaction(
        [owner], {int(owner.virtual_machine_id)}
    ) as context:
        actor = _actor(None, owner)
        credential_ids = _credential_ids(context, before)
        rows = context.assignments[int(owner.virtual_machine_id)]
        _remove_retired_assignments(rows, set(), credential_ids, actor)
        _restore_reference_fields(owner, dict.fromkeys(before))
        original_save = getattr(type(owner).save, "_proxbox_cloudinit_original", None)
        if original_save is None:
            raise ValidationError("The cloud-init credential writer is not installed.")
        _persist_reference_fields(owner, original_save)
        return original(owner, *args, **kwargs)


@sensitive_variables()
def delete_cloudinit_owner(
    owner: Any, original: Callable, args: tuple[Any, ...], kwargs: dict[str, Any]
) -> Any:
    before = _references(owner)
    if not any(before.values()) and not _has_owned_assignments(owner):
        return original(owner, *args, **kwargs)
    _require_default_database(owner, kwargs)
    try:
        return _delete_with_context(owner, original, args, kwargs, before)
    except BaseException:
        _restore_reference_fields(owner, before)
        raise


def install_cloudinit_material_writer() -> None:
    """Install the model save/delete provider boundary once."""
    from netbox_proxbox.models import ProxmoxVMCloudInit

    if getattr(ProxmoxVMCloudInit.save, "_proxbox_cloudinit_writer", False):
        return
    original_save = ProxmoxVMCloudInit.save
    original_delete = ProxmoxVMCloudInit.delete

    @sensitive_variables()
    @wraps(original_save)
    def save(instance: Any, *args: Any, **kwargs: Any) -> Any:
        return save_cloudinit_owner(instance, original_save, args, kwargs)

    @sensitive_variables()
    @wraps(original_delete)
    def delete(instance: Any, *args: Any, **kwargs: Any) -> Any:
        return delete_cloudinit_owner(instance, original_delete, args, kwargs)

    save._proxbox_cloudinit_writer = True
    save._proxbox_cloudinit_original = original_save
    delete._proxbox_cloudinit_writer = True
    ProxmoxVMCloudInit.save = save
    ProxmoxVMCloudInit.delete = delete
