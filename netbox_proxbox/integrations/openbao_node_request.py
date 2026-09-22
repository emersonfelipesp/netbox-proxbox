"""Outer request boundaries for node material mutations."""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from typing import Any

from django.core.exceptions import ValidationError
from django.views.decorators.debug import sensitive_variables

from .openbao_node_pending import SLOTS
from .openbao_node_transaction import (
    node_request_actor_scope,
    node_request_material_boundary,
)


def mark_node_material_request_sensitive(request: Any) -> None:
    """Redact all submitted material if an unexpected traceback escapes."""
    request.sensitive_post_parameters = "__ALL__"
    underlying = getattr(request, "_request", None)
    if underlying is not None:
        underlying.sensitive_post_parameters = "__ALL__"


@sensitive_variables()
def request_pk(value: Any) -> int | None:
    """Extract a positive primary key from DRF or form relation input."""
    if isinstance(value, Mapping):
        value = value.get("id")
    if isinstance(value, bool):
        return None
    try:
        result = int(value)
    except (TypeError, ValueError):
        return None
    return result if result > 0 else None


@sensitive_variables()
def requested_node_ids(
    payloads: Sequence[Mapping[str, Any]],
    owners: Sequence[Any],
) -> set[int]:
    """Collect current and proposed node IDs before framework persistence."""
    result = {owner.node_id for owner in owners if owner.node_id is not None}
    for payload in payloads:
        node_id = request_pk(payload.get("node", payload.get("node_id")))
        if node_id is not None:
            result.add(node_id)
    return result


def _node_ids_use_openbao(node_ids: set[int]) -> bool:
    from netbox_proxbox.models import NodeSSHCredential, ProxmoxNode

    from .openbao import node_uses_openbao_storage

    nodes = ProxmoxNode.objects.select_related("endpoint").filter(pk__in=node_ids)
    return any(
        node_uses_openbao_storage(NodeSSHCredential(node=node)) for node in nodes
    )


def _owners_require_boundary(owners: Sequence[Any]) -> bool:
    from .openbao import node_uses_openbao_storage
    from .openbao_node_writer import _has_owned_assignments

    for owner in owners:
        if node_uses_openbao_storage(owner):
            return True
        if any(getattr(owner, name, None) for name in SLOTS):
            return True
        if _has_owned_assignments(owner):
            return True
    return False


@contextmanager
@sensitive_variables()
def node_credential_request_boundary(
    owners: Sequence[Any],
    payloads: Sequence[Mapping[str, Any]],
    *,
    actor: Any,
    request: Any = None,
    allow_new: bool = False,
) -> Iterator[None]:
    """Wrap the complete NetBox mutation when OpenBao state can be touched."""
    if request is not None:
        mark_node_material_request_sensitive(request)
    node_ids = requested_node_ids(payloads, owners)
    requires_material = _owners_require_boundary(owners)
    if not requires_material:
        requires_material = _node_ids_use_openbao(node_ids)
    if not requires_material:
        with node_request_actor_scope(actor, request):
            yield
        return
    if allow_new and not node_ids:
        raise ValidationError(
            "A declared Proxmox node is required before OpenBao material access."
        )
    with node_request_material_boundary(
        owners,
        actor=actor,
        request=request,
        allow_new=allow_new,
        new_node_ids=node_ids,
    ):
        yield


@contextmanager
def node_link_request_boundary(
    nodes: Sequence[Any],
    payloads: Sequence[Mapping[str, Any]],
    *,
    actor: Any,
    request: Any = None,
) -> Iterator[None]:
    """Wrap REST node-link changes that reconcile an existing owner."""
    from netbox_proxbox.models import NodeSSHCredential

    owners = list(
        NodeSSHCredential.objects.select_related("node", "node__endpoint")
        .filter(node_id__in=[node.pk for node in nodes])
        .order_by("pk")
    )
    affected = owners if _owners_require_boundary(owners) else []
    if not affected:
        with node_request_actor_scope(actor, request):
            yield
        return
    device_ids = {
        device_id
        for payload in payloads
        if (
            device_id := request_pk(
                payload.get("netbox_device", payload.get("netbox_device_id"))
            )
        )
        is not None
    }
    with node_request_material_boundary(
        affected,
        actor=actor,
        request=request,
        target_device_ids=device_ids,
    ):
        yield
