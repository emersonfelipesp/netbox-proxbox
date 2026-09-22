"""Outer UI and REST boundaries for one-secret owner mutations."""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from typing import Any

from django.views.decorators.debug import sensitive_variables

from .openbao_single_pending import spec_for
from .openbao_single_transaction import (
    single_secret_actor_scope,
    single_secret_request_boundary,
)


def mark_single_secret_request_sensitive(request: Any) -> None:
    """Redact every submitted value from unexpected traceback pages."""
    request.sensitive_post_parameters = "__ALL__"
    underlying = getattr(request, "_request", None)
    if underlying is not None:
        underlying.sensitive_post_parameters = "__ALL__"


def _payload_has_material(payloads: Sequence[Mapping[str, Any]], field: str) -> bool:
    return any(field in payload for payload in payloads)


def _owners_have_state(owners: Sequence[Any]) -> bool:
    from .openbao_single_writer import _has_owned_assignments

    return any(
        getattr(owner, spec_for(owner).reference_field, None) is not None
        or _has_owned_assignments(owner)
        for owner in owners
    )


@contextmanager
@sensitive_variables()
def single_secret_mutation_boundary(
    owners: Sequence[Any],
    payloads: Sequence[Mapping[str, Any]],
    *,
    model: type,
    material_field: str,
    actor: Any,
    request: Any = None,
    allow_new: bool = False,
) -> Iterator[None]:
    """Begin provider compensation only when a mutation can touch material."""
    if request is not None:
        mark_single_secret_request_sensitive(request)
    from .openbao_single import owner_uses_openbao_storage

    probe = owners[0] if owners else model()
    requires_material = _owners_have_state(owners)
    requires_material = requires_material or (
        owner_uses_openbao_storage(probe)
        and (
            _payload_has_material(payloads, material_field)
            or (allow_new and model._meta.model_name == "fastapiendpoint")
        )
    )
    if not requires_material:
        with single_secret_actor_scope(actor, request):
            yield
        return
    new_models = {model} if allow_new else set()
    with single_secret_request_boundary(
        owners,
        actor=actor,
        request=request,
        new_models=new_models,
    ):
        yield
