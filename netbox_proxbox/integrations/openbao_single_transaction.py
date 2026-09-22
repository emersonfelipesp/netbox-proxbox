"""Predeclare ownership for one-secret provider transactions."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction

from .openbao_single_pending import spec_for


def _owner_key(owner: Any) -> tuple[str, int]:
    return owner._meta.label_lower, int(owner.pk)


@dataclass
class SingleSecretMaterialContext:
    """Locked owner, assignment, credential, and policy graph."""

    settings: Any
    owners: dict[tuple[str, int], Any]
    assignments: dict[tuple[str, int], list[Any]]
    credentials: dict[str, Any]
    policy: Any
    content_types: dict[str, Any]
    allow_new_models: set[str] = field(default_factory=set)
    new_instances: dict[int, Any] = field(default_factory=dict, repr=False)
    intents: dict[tuple[str, int], Any] = field(default_factory=dict, repr=False)

    def admit(self, owner: Any) -> None:
        """Refuse owners omitted from the graph acquired before persistence."""
        if self.new_instances.get(id(owner)) is owner:
            return
        if owner.pk is not None and _owner_key(owner) in self.owners:
            return
        label = owner._meta.label_lower
        if label in self.allow_new_models and owner.pk is None and owner._state.adding:
            self.new_instances[id(owner)] = owner
            return
        raise ValidationError(
            "Credential ownership was not declared before OpenBao material access."
        )

    def content_type_for(self, owner: Any) -> Any:
        """Return the locked assignment target type for one owner."""
        try:
            return self.content_types[owner._meta.label_lower]
        except KeyError as exc:
            raise ValidationError(
                "Credential owner type was not declared before assignment access."
            ) from exc

    def declare_intent(self, owner: Any, intent: Any) -> None:
        """Expose an explicit intent to same-row transition snapshots."""
        if owner.pk is not None:
            self.intents[_owner_key(owner)] = intent

    def intent_for(self, owner: Any) -> Any | None:
        """Return a declared intent for another snapshot of the same owner."""
        if owner.pk is None:
            return None
        return self.intents.get(_owner_key(owner))


_CURRENT: ContextVar[SingleSecretMaterialContext | None] = ContextVar(
    "proxbox_single_secret_material_context", default=None
)
_REQUEST_ACTOR: ContextVar[Any | None] = ContextVar(
    "proxbox_single_secret_request_actor", default=None
)
_REQUEST: ContextVar[Any | None] = ContextVar(
    "proxbox_single_secret_request", default=None
)


def current_single_secret_context() -> SingleSecretMaterialContext | None:
    return _CURRENT.get()


def current_single_secret_actor() -> Any | None:
    return _REQUEST_ACTOR.get()


def current_single_secret_request() -> Any | None:
    return _REQUEST.get()


@contextmanager
def single_secret_actor_scope(actor: Any, request: Any = None) -> Iterator[None]:
    """Attribute a request that does not need provider material."""
    actor_token = _REQUEST_ACTOR.set(actor)
    request_token = _REQUEST.set(request)
    try:
        yield
    finally:
        _REQUEST.reset(request_token)
        _REQUEST_ACTOR.reset(actor_token)


def _locked_settings() -> Any:
    from netbox_proxbox.models import ProxboxPluginSettings

    settings = (
        ProxboxPluginSettings.objects.select_for_update()
        .filter(singleton_key="default")
        .first()
    )
    if settings is None:
        raise ValidationError(
            "Persist Proxbox plugin settings before OpenBao material access."
        )
    return settings


def _group_owners(owners: Sequence[Any]) -> dict[type, list[Any]]:
    grouped: dict[type, list[Any]] = {}
    for owner in owners:
        spec_for(owner)
        grouped.setdefault(type(owner), []).append(owner)
    return grouped


def _lock_owner_group(model: type, observed: list[Any]) -> dict[tuple[str, int], Any]:
    ids = {owner.pk for owner in observed if owner.pk is not None}
    locked = {
        _owner_key(owner): owner
        for owner in model.objects.select_for_update().filter(pk__in=ids).order_by("pk")
    }
    if len(locked) != len(ids):
        raise ValidationError("A declared credential owner no longer exists.")
    for owner in observed:
        if owner.pk is None:
            continue
        previous = locked[_owner_key(owner)]
        field = spec_for(owner).reference_field
        if getattr(owner, field) != getattr(previous, field):
            raise ValidationError(
                "A credential reference changed before ownership was acquired."
            )
    return locked


def _locked_owners(owners: Sequence[Any]) -> dict[tuple[str, int], Any]:
    result: dict[tuple[str, int], Any] = {}
    for model, observed in sorted(
        _group_owners(owners).items(), key=lambda item: item[0]._meta.label_lower
    ):
        result.update(_lock_owner_group(model, observed))
    return result


def _content_types(models: set[type]) -> dict[str, Any]:
    from django.contrib.contenttypes.models import ContentType

    return {
        model._meta.label_lower: ContentType.objects.get_for_model(model)
        for model in sorted(models, key=lambda item: item._meta.label_lower)
    }


def _locked_assignments(
    owners: dict[tuple[str, int], Any], content_types: dict[str, Any]
) -> dict[tuple[str, int], list[Any]]:
    from netbox_openbao.models import CredentialAssignment

    result = {key: [] for key in owners}
    for label, content_type in content_types.items():
        owner_ids = [pk for owner_label, pk in owners if owner_label == label]
        if not owner_ids:
            continue
        sample = next(owner for key, owner in owners.items() if key[0] == label)
        purpose = spec_for(sample).purpose
        rows = (
            CredentialAssignment.objects.select_for_update()
            .filter(
                assigned_object_type=content_type,
                assigned_object_id__in=owner_ids,
                purpose=purpose,
            )
            .order_by("pk")
        )
        for assignment in rows:
            result[(label, int(assignment.assigned_object_id))].append(assignment)
    return result


def _existing_credentials(
    owners: dict[tuple[str, int], Any], assignments: dict[tuple[str, int], list[Any]]
) -> list[Any]:
    from django.db.models import Q
    from netbox_openbao.models import Credential

    references = {
        str(reference)
        for owner in owners.values()
        if (reference := getattr(owner, spec_for(owner).reference_field)) is not None
    }
    assigned_ids = {
        assignment.credential_id for rows in assignments.values() for assignment in rows
    }
    credentials = list(
        Credential.objects.filter(Q(uuid__in=references) | Q(pk__in=assigned_ids))
    )
    found_references = {str(row.uuid) for row in credentials}
    found_ids = {row.pk for row in credentials}
    if not references.issubset(found_references):
        raise ValidationError("An existing credential reference cannot be resolved.")
    if not assigned_ids.issubset(found_ids):
        raise ValidationError("An assigned credential no longer exists.")
    return credentials


def _declare_context(
    owners: Sequence[Any], new_models: set[type]
) -> SingleSecretMaterialContext:
    from netbox_openbao.synchronization import lock_material_subjects

    from .openbao import _default_policy

    settings = _locked_settings()
    locked_owners = _locked_owners(owners)
    models = {type(owner) for owner in owners} | new_models
    content_types = _content_types(models)
    assignments = _locked_assignments(locked_owners, content_types)
    subjects = _existing_credentials(locked_owners, assignments)
    policy = _default_policy()
    policy_identity = (policy.pk, policy.engine_id)
    locked_subjects = lock_material_subjects(
        subjects, additional_policy_ids={policy.pk}
    )
    policy = _default_policy()
    if (policy.pk, policy.engine_id) != policy_identity:
        raise ValidationError(
            "The default OpenBao policy changed during ownership acquisition."
        )
    return SingleSecretMaterialContext(
        settings=settings,
        owners=locked_owners,
        assignments=assignments,
        credentials={str(row.uuid): row for row in locked_subjects.values()},
        policy=policy,
        content_types=content_types,
        allow_new_models={model._meta.label_lower for model in new_models},
    )


def _material_transaction_factory() -> Any:
    try:
        from netbox_openbao.material_transactions import (
            MATERIAL_TRANSACTION_CONTRACT_VERSION,
            material_transaction,
        )
    except ImportError as exc:
        raise ValidationError(
            "OpenBao credential material requires netbox-openbao 0.1.0 or newer "
            "with material transaction contract version 1."
        ) from exc
    if MATERIAL_TRANSACTION_CONTRACT_VERSION != 1:
        raise ValidationError(
            "A compatible OpenBao material transaction contract is required."
        )
    return material_transaction


@contextmanager
def single_secret_material_transaction(
    owners: Sequence[Any], *, new_models: set[type] | None = None
) -> Iterator[SingleSecretMaterialContext]:
    """Begin provider compensation before NetBox's database atomic block."""
    declared_models = new_models or set()
    existing = _CURRENT.get()
    if existing is not None:
        for owner in owners:
            existing.admit(owner)
        missing = {
            model._meta.label_lower for model in declared_models
        } - existing.allow_new_models
        if missing:
            raise ValidationError(
                "Credential owner type was not declared before material access."
            )
        yield existing
        return
    if transaction.get_connection("default").in_atomic_block:
        raise ValidationError(
            "OpenBao credential material requires its provider transaction to begin "
            "before the NetBox database transaction. Use the supported UI or API "
            "material request boundary."
        )
    material_transaction = _material_transaction_factory()
    with material_transaction():
        context = _declare_context(owners, declared_models)
        for owner in owners:
            context.admit(owner)
        token = _CURRENT.set(context)
        try:
            yield context
        finally:
            _CURRENT.reset(token)


@contextmanager
def single_secret_request_boundary(
    owners: Sequence[Any],
    *,
    actor: Any,
    request: Any = None,
    new_models: set[type] | None = None,
) -> Iterator[SingleSecretMaterialContext]:
    """Own provider compensation and actor context for a complete mutation."""
    actor_token = _REQUEST_ACTOR.set(actor)
    request_token = _REQUEST.set(request)
    try:
        with single_secret_material_transaction(
            owners, new_models=new_models
        ) as context:
            yield context
    finally:
        _REQUEST.reset(request_token)
        _REQUEST_ACTOR.reset(actor_token)
