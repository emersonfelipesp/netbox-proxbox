"""Declare endpoint ownership before entering the provider material graph."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from django.core.exceptions import ValidationError

from .openbao_pending import SLOTS


@dataclass
class EndpointMaterialContext:
    settings: Any
    endpoints: dict[int, Any]
    credentials: dict[str, Any]
    policy: Any
    content_type: Any
    allow_new: bool = False
    new_instances: dict[int, Any] = field(default_factory=dict, repr=False)

    def admit(self, endpoint: Any) -> None:
        """Refuse undeclared existing owners, including mid-batch objects."""
        if (
            self.new_instances.get(id(endpoint)) is endpoint
            or endpoint.pk in self.endpoints
        ):
            return
        if self.allow_new and endpoint.pk is None and endpoint._state.adding:
            self.new_instances[id(endpoint)] = endpoint
            return
        raise ValidationError(
            "Endpoint ownership was not declared before material access."
        )


_CURRENT: ContextVar[EndpointMaterialContext | None] = ContextVar(
    "proxbox_endpoint_material_context",
    default=None,
)


def current_endpoint_material_context() -> EndpointMaterialContext | None:
    return _CURRENT.get()


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
            "Endpoint credential references changed before ownership was acquired."
        )


def _locked_endpoints(endpoints: Sequence[Any]) -> dict[int, Any]:
    from netbox_proxbox.models import ProxmoxEndpoint

    ids = {endpoint.pk for endpoint in endpoints if endpoint.pk is not None}
    locked = {
        endpoint.pk: endpoint
        for endpoint in ProxmoxEndpoint.objects.select_for_update()
        .filter(pk__in=ids)
        .order_by("pk")
    }
    if locked.keys() != ids:
        raise ValidationError("A declared endpoint no longer exists.")
    for endpoint in endpoints:
        if endpoint.pk is not None:
            _check_references(endpoint, locked[endpoint.pk])
    return locked


def _assignment_credentials(content_type: Any, endpoint_ids: Sequence[int]) -> set[int]:
    from netbox_openbao.models import CredentialAssignment

    return set(
        CredentialAssignment.objects.filter(
            assigned_object_type=content_type,
            assigned_object_id__in=endpoint_ids,
        ).values_list("credential_id", flat=True)
    )


def _existing_credentials(
    endpoints: dict[int, Any], assigned_ids: set[int]
) -> list[Any]:
    from django.db.models import Q
    from netbox_openbao.models import Credential

    references = {
        str(value)
        for endpoint in endpoints.values()
        for name in SLOTS
        if (value := getattr(endpoint, name)) is not None
    }
    credentials = list(
        Credential.objects.filter(Q(uuid__in=references) | Q(pk__in=assigned_ids))
    )
    if not references.issubset({str(row.uuid) for row in credentials}):
        raise ValidationError(
            "An existing endpoint credential reference cannot be resolved."
        )
    if not assigned_ids.issubset({row.pk for row in credentials}):
        raise ValidationError("An assigned endpoint credential no longer exists.")
    return credentials


def _declare_context(
    endpoints: Sequence[Any],
    *,
    allow_new: bool,
) -> EndpointMaterialContext:
    from django.contrib.contenttypes.models import ContentType
    from netbox_openbao.synchronization import lock_material_subjects

    from netbox_proxbox.models import ProxmoxEndpoint

    from .openbao import _default_policy

    settings = _locked_settings()
    owners = _locked_endpoints(endpoints)
    content_type = ContentType.objects.get_for_model(ProxmoxEndpoint)
    assigned_ids = _assignment_credentials(content_type, tuple(owners))
    subjects = _existing_credentials(owners, assigned_ids)
    policy = _default_policy()
    policy_identity = (policy.pk, policy.engine_id)
    locked = lock_material_subjects(subjects, additional_policy_ids={policy.pk})
    policy = _default_policy()
    if (policy.pk, policy.engine_id) != policy_identity:
        raise ValidationError(
            "The default OpenBao policy changed during ownership acquisition."
        )
    if _assignment_credentials(content_type, tuple(owners)) != assigned_ids:
        raise ValidationError(
            "Endpoint credential assignments changed during ownership acquisition."
        )
    return EndpointMaterialContext(
        settings,
        owners,
        {str(row.uuid): row for row in locked.values()},
        policy,
        content_type,
        allow_new=allow_new,
    )


@contextmanager
def endpoint_material_transaction(
    endpoints: Sequence[Any],
    *,
    allow_new: bool = False,
) -> Iterator[EndpointMaterialContext]:
    """Enter outside framework atomics and predeclare the complete owner graph."""
    try:
        from netbox_openbao.material_transactions import (
            MATERIAL_TRANSACTION_CONTRACT_VERSION,
            material_transaction,
        )
    except ImportError as exc:
        raise ValidationError(
            "OpenBao endpoint material requires netbox-openbao 0.1.0 or newer "
            "with material transaction contract version 1."
        ) from exc

    if MATERIAL_TRANSACTION_CONTRACT_VERSION != 1:
        raise ValidationError(
            "A compatible OpenBao material transaction contract is required."
        )
    with material_transaction():
        existing = _CURRENT.get()
        if existing is not None:
            for endpoint in endpoints:
                existing.admit(endpoint)
            yield existing
            return
        context = _declare_context(endpoints, allow_new=allow_new)
        for endpoint in endpoints:
            context.admit(endpoint)
        token = _CURRENT.set(context)
        try:
            yield context
        finally:
            _CURRENT.reset(token)
