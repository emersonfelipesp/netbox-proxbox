"""Declare node SSH ownership before entering the provider material graph."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction

from .openbao_node_pending import SLOTS


@dataclass
class NodeMaterialContext:
    settings: Any
    owners: dict[int, Any]
    related_owners: dict[int, Any]
    credentials: dict[str, Any]
    policy: Any
    content_type: Any
    nodes: dict[int, Any]
    original_node_device_ids: dict[int, int | None] = field(default_factory=dict)
    device_ids: set[int] = field(default_factory=set)
    allow_new: bool = False
    allowed_new_node_ids: set[int] = field(default_factory=set)
    new_instances: dict[int, Any] = field(default_factory=dict, repr=False)

    def admit(self, credential: Any) -> None:
        """Refuse undeclared existing owners, including mid-batch objects."""
        if (
            self.new_instances.get(id(credential)) is credential
            or credential.pk in self.owners
        ):
            return
        if (
            self.allow_new
            and credential.pk is None
            and credential._state.adding
            and credential.node_id in self.allowed_new_node_ids
        ):
            self.new_instances[id(credential)] = credential
            return
        raise ValidationError(
            "Node SSH credential ownership was not declared before material access."
        )

    def device_id(self, credential: Any) -> int | None:
        """Return the locked NetBox device target for the owner's selected node."""
        node = self.nodes.get(credential.node_id)
        if node is None:
            raise ValidationError("The declared Proxmox node no longer exists.")
        return node.netbox_device_id

    def admit_targets(self, device_ids: set[int]) -> None:
        """Refuse device targets omitted from the predeclared lock graph."""
        if not device_ids.issubset(self.device_ids):
            raise ValidationError(
                "NetBox device ownership was not declared before assignment access."
            )

    def owner_device_ids(self, credential: Any) -> set[int]:
        """Return only this owner's locked previous and current device targets."""
        node_ids = {credential.node_id}
        previous = self.owners.get(credential.pk)
        if previous is not None:
            node_ids.add(previous.node_id)
        device_ids = {
            self.original_node_device_ids.get(node_id) for node_id in node_ids
        }
        device_ids.update(
            node.netbox_device_id
            for node_id in node_ids
            if (node := self.nodes.get(node_id)) is not None
        )
        return {device_id for device_id in device_ids if device_id is not None}

    def assignment_selected_elsewhere(
        self,
        owner: Any,
        credential_id: int,
        device_id: int,
    ) -> bool:
        """Return whether another locked owner still selects this assignment."""
        for candidate in self.related_owners.values():
            if candidate.pk == owner.pk:
                continue
            node = self.nodes.get(candidate.node_id)
            if node is None or node.netbox_device_id != device_id:
                continue
            reference_field = {
                "password": "openbao_password_credential_uuid",
                "key": "openbao_keypair_credential_uuid",
            }.get(candidate.auth_method)
            if reference_field is None:
                continue
            reference = getattr(candidate, reference_field)
            selected = self.credentials.get(str(reference))
            if selected is not None and selected.pk == credential_id:
                return True
        return False


_CURRENT: ContextVar[NodeMaterialContext | None] = ContextVar(
    "proxbox_node_material_context",
    default=None,
)
_REQUEST_ACTOR: ContextVar[Any | None] = ContextVar(
    "proxbox_node_material_request_actor",
    default=None,
)
_REQUEST: ContextVar[Any | None] = ContextVar(
    "proxbox_node_material_request",
    default=None,
)


def current_node_material_context() -> NodeMaterialContext | None:
    return _CURRENT.get()


def current_node_request_actor() -> Any | None:
    """Return the actor installed by the outer UI or API mutation boundary."""
    return _REQUEST_ACTOR.get()


def current_node_request() -> Any | None:
    """Return the request installed by the outer mutation boundary."""
    return _REQUEST.get()


@contextmanager
def node_request_actor_scope(actor: Any, request: Any = None) -> Iterator[None]:
    """Attribute a request even when it does not require provider material."""
    token = _REQUEST_ACTOR.set(actor)
    request_token = _REQUEST.set(request)
    try:
        yield
    finally:
        _REQUEST.reset(request_token)
        _REQUEST_ACTOR.reset(token)


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


def _check_references(observed: Any, locked: Any) -> None:
    if any(getattr(observed, name) != getattr(locked, name) for name in SLOTS):
        raise ValidationError(
            "Node SSH credential references changed before ownership was acquired."
        )


def _locked_owners(credentials: Sequence[Any]) -> dict[int, Any]:
    from netbox_proxbox.models import NodeSSHCredential

    ids = {credential.pk for credential in credentials if credential.pk is not None}
    locked = {
        credential.pk: credential
        for credential in NodeSSHCredential.objects.select_for_update()
        .filter(pk__in=ids)
        .order_by("pk")
    }
    if locked.keys() != ids:
        raise ValidationError("A declared node SSH credential no longer exists.")
    for credential in credentials:
        if credential.pk is not None:
            _check_references(credential, locked[credential.pk])
    return locked


def _locked_nodes(
    credentials: Sequence[Any],
    owners: dict[int, Any],
    related_owners: dict[int, Any],
    additional_ids: set[int],
) -> dict[int, Any]:
    from netbox_proxbox.models import ProxmoxNode

    node_ids = {credential.node_id for credential in credentials}
    node_ids.update(owner.node_id for owner in owners.values())
    node_ids.update(owner.node_id for owner in related_owners.values())
    node_ids.update(additional_ids)
    nodes = {
        node.pk: node
        for node in ProxmoxNode.objects.select_for_update()
        .filter(pk__in=node_ids)
        .order_by("pk")
    }
    if nodes.keys() != node_ids:
        raise ValidationError("A declared Proxmox node no longer exists.")
    return nodes


def _lock_devices(nodes: dict[int, Any], additional_ids: set[int]) -> set[int]:
    from dcim.models import Device

    device_ids = {
        node.netbox_device_id for node in nodes.values() if node.netbox_device_id
    }
    device_ids.update(additional_ids)
    locked_ids = set(
        Device.objects.select_for_update()
        .filter(pk__in=device_ids)
        .order_by("pk")
        .values_list("pk", flat=True)
    )
    if locked_ids != device_ids:
        raise ValidationError("A declared NetBox device no longer exists.")
    return locked_ids


def _reference_values(owners: Sequence[Any]) -> set[str]:
    return {
        str(value)
        for owner in owners
        for name in SLOTS
        if (value := getattr(owner, name)) is not None
    }


def _locked_related_owners(owners: dict[int, Any]) -> dict[int, Any]:
    """Lock owners that select credentials in the declared ownership graph."""
    from django.db.models import Q
    from netbox_proxbox.models import NodeSSHCredential

    references = _reference_values(list(owners.values()))
    if not references:
        return {}
    related = (
        NodeSSHCredential.objects.select_for_update()
        .filter(
            Q(
                auth_method="password",
                openbao_password_credential_uuid__in=references,
            )
            | Q(
                auth_method="key",
                openbao_keypair_credential_uuid__in=references,
            )
        )
        .order_by("pk")
    )
    return {owner.pk: owner for owner in related}


def _existing_credentials(owners: Sequence[Any]) -> list[Any]:
    from netbox_openbao.models import Credential

    references = _reference_values(owners)
    credentials = list(Credential.objects.filter(uuid__in=references))
    if references != {str(row.uuid) for row in credentials}:
        raise ValidationError(
            "An existing node SSH credential reference cannot be resolved."
        )
    return credentials


def _declare_context(
    credentials: Sequence[Any],
    *,
    allow_new: bool,
    new_node_ids: set[int],
    target_device_ids: set[int],
) -> NodeMaterialContext:
    from dcim.models import Device
    from django.contrib.contenttypes.models import ContentType
    from netbox_openbao.synchronization import lock_material_subjects

    from .openbao import _default_policy

    settings = _locked_settings()
    owners = _locked_owners(credentials)
    related_owners = _locked_related_owners(owners)
    nodes = _locked_nodes(credentials, owners, related_owners, new_node_ids)
    device_ids = _lock_devices(nodes, target_device_ids)
    policy = _default_policy()
    policy_identity = (policy.pk, policy.engine_id)
    subjects = _existing_credentials([*owners.values(), *related_owners.values()])
    locked = lock_material_subjects(subjects, additional_policy_ids={policy.pk})
    policy = _default_policy()
    if (policy.pk, policy.engine_id) != policy_identity:
        raise ValidationError(
            "The default OpenBao policy changed during ownership acquisition."
        )
    return NodeMaterialContext(
        settings=settings,
        owners=owners,
        related_owners=related_owners,
        credentials={str(row.uuid): row for row in locked.values()},
        policy=policy,
        content_type=ContentType.objects.get_for_model(Device),
        nodes=nodes,
        original_node_device_ids={
            node_id: node.netbox_device_id for node_id, node in nodes.items()
        },
        device_ids=device_ids,
        allow_new=allow_new,
        allowed_new_node_ids=new_node_ids,
    )


def _admit_existing_context(
    context: NodeMaterialContext,
    credentials: Sequence[Any],
    declared_new_nodes: set[int],
    target_device_ids: set[int],
) -> None:
    context.admit_targets(target_device_ids)
    if not declared_new_nodes.issubset(context.allowed_new_node_ids):
        raise ValidationError(
            "Node SSH credential ownership was not declared before material access."
        )
    for credential in credentials:
        context.admit(credential)


def _material_transaction_factory() -> Any:
    try:
        from netbox_openbao.material_transactions import (
            MATERIAL_TRANSACTION_CONTRACT_VERSION,
            material_transaction,
        )
    except ImportError as exc:
        raise ValidationError(
            "OpenBao node SSH material requires netbox-openbao 0.1.0 or newer "
            "with material transaction contract version 1."
        ) from exc
    if MATERIAL_TRANSACTION_CONTRACT_VERSION != 1:
        raise ValidationError(
            "A compatible OpenBao material transaction contract is required."
        )
    return material_transaction


@contextmanager
def node_material_transaction(
    credentials: Sequence[Any],
    *,
    allow_new: bool = False,
    new_node_ids: set[int] | None = None,
    target_device_ids: set[int] | None = None,
) -> Iterator[NodeMaterialContext]:
    """Enter outside framework atomics and predeclare the complete owner graph."""
    declared_new_nodes = new_node_ids or set()
    existing = _CURRENT.get()
    if existing is not None:
        _admit_existing_context(
            existing,
            credentials,
            declared_new_nodes,
            target_device_ids or set(),
        )
        yield existing
        return
    if transaction.get_connection("default").in_atomic_block:
        raise ValidationError(
            "OpenBao node material requires its provider transaction to begin "
            "before the NetBox database transaction. Use the supported UI, API, "
            "or node material request boundary."
        )
    material_transaction = _material_transaction_factory()
    with material_transaction():
        context = _declare_context(
            credentials,
            allow_new=allow_new,
            new_node_ids=declared_new_nodes,
            target_device_ids=target_device_ids or set(),
        )
        for credential in credentials:
            context.admit(credential)
        token = _CURRENT.set(context)
        try:
            yield context
        finally:
            _CURRENT.reset(token)


@contextmanager
def node_request_material_boundary(
    credentials: Sequence[Any],
    *,
    actor: Any,
    request: Any = None,
    allow_new: bool = False,
    new_node_ids: set[int] | None = None,
    target_device_ids: set[int] | None = None,
) -> Iterator[NodeMaterialContext]:
    """Own provider compensation outside NetBox's UI/API atomic blocks."""
    actor_token = _REQUEST_ACTOR.set(actor)
    request_token = _REQUEST.set(request)
    try:
        with node_material_transaction(
            credentials,
            allow_new=allow_new,
            new_node_ids=new_node_ids,
            target_device_ids=target_device_ids,
        ) as context:
            yield context
    finally:
        _REQUEST.reset(request_token)
        _REQUEST_ACTOR.reset(actor_token)
