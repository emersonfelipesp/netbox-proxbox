"""Optional OpenBao material handling for service-owned SSH credentials."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any, Literal

from django.core.exceptions import ObjectDoesNotExist, PermissionDenied, ValidationError
from django.views.decorators.debug import sensitive_variables

from netbox_proxbox.integrations.openbao import (
    _credential_name,
    _default_policy,
    is_netbox_openbao_installed,
    reveal_credential_material,
)

_PENDING_ATTRIBUTE = "_proxbox_service_openbao_pending"
_SLOTS = {
    "password": (
        "openbao_password_credential_uuid",
        "ssh-password",
        "password",
    ),
    "private_key": (
        "openbao_keypair_credential_uuid",
        "ssh-keypair",
        "private_key",
    ),
}


def _service_references(owner: Any) -> tuple[Any, Any]:
    return tuple(getattr(owner, slot[0], None) for slot in _SLOTS.values())


def assert_service_intent(owner: Any, expected_references: tuple[Any, Any]) -> None:
    """Reject a service write whose credential references became stale."""
    if getattr(owner, "pk", None) is None:
        return
    from netbox_proxbox.models import ServiceSSHCredential

    locked = ServiceSSHCredential.objects.select_for_update().get(pk=owner.pk)
    if _service_references(locked) != tuple(expected_references):
        raise ValidationError(
            "The service credential changed before the requested update."
        )


def validate_service_storage(owner: Any) -> None:
    """Revalidate service storage against the transaction-locked settings row."""
    from netbox_proxbox.integrations.openbao import validate_locked_openbao_storage
    from .openbao_transaction import current_endpoint_material_context

    context = current_endpoint_material_context()
    if context is None:
        raise ValidationError(
            "OpenBao service material requires the outer request transaction."
        )
    validate_locked_openbao_storage(
        context.settings,
        endpoint_override=owner.storage_backend,
        conflict_message="The service credential storage selection changed.",
    )


def _service_uses_openbao(endpoint: Any) -> bool:
    try:
        credential = endpoint.ssh_service.ssh_credential
    except (AttributeError, ObjectDoesNotExist):
        return False
    return credential.storage_backend == "openbao" or any(
        _service_references(credential)
    )


def _request_requires_provider(endpoint: Any, payload: Mapping[str, Any]) -> bool:
    if payload.get("ssh_storage") in {"openbao_new", "openbao_existing"}:
        return True
    if _service_uses_openbao(endpoint):
        return True
    from netbox_proxbox.integrations.openbao import (
        effective_credential_storage_backend,
    )

    if effective_credential_storage_backend(endpoint) == "openbao":
        return True
    if "credential_storage_backend" not in payload:
        return False
    submitted = str(payload.get("credential_storage_backend") or "")
    return not submitted or submitted == "openbao"


def _validate_submitted_endpoint_storage(
    payload: Mapping[str, Any], settings: Any
) -> None:
    """Revalidate a submitted OpenBao or inherited selection under the lock."""
    if "credential_storage_backend" not in payload:
        return
    from netbox_proxbox.choices import CredentialStorageBackendChoices
    from netbox_proxbox.integrations.openbao import validate_locked_openbao_storage

    submitted = str(payload.get("credential_storage_backend") or "")
    locked_backend = submitted or str(
        getattr(settings, "credential_storage_backend", "") or ""
    )
    if locked_backend != CredentialStorageBackendChoices.OPENBAO:
        return
    validate_locked_openbao_storage(
        settings,
        endpoint_override=submitted,
        conflict_message="The endpoint credential storage selection changed.",
    )


@contextmanager
def service_chain_request_boundary(
    endpoint: Any,
    payload: Mapping[str, Any],
    *,
    actor: Any,
    request: Any = None,
) -> Iterator[None]:
    """Enter the provider transaction before NetBox's edit transaction."""
    endpoint._openbao_actor_user = _require_actor(actor)
    if request is not None:
        request.sensitive_post_parameters = "__ALL__"
    if not is_netbox_openbao_installed() or not _request_requires_provider(
        endpoint, payload
    ):
        yield
        return
    from .openbao_transaction import endpoint_material_transaction

    creating = getattr(endpoint, "pk", None) is None
    declared = [] if creating else [endpoint]
    with endpoint_material_transaction(declared, allow_new=creating) as context:
        _validate_submitted_endpoint_storage(payload, context.settings)
        yield


@sensitive_variables()
def queue_service_secret(
    owner: Any,
    kind: Literal["password", "private_key"],
    plaintext: str,
    *,
    user: Any = None,
    request: Any = None,
) -> None:
    """Queue service material without placing it in a model field."""
    if kind not in _SLOTS:
        raise ValueError("Unsupported service SSH credential slot.")
    pending = dict(getattr(owner, _PENDING_ATTRIBUTE, {}))
    pending[kind] = (plaintext, user, request)
    setattr(owner, _PENDING_ATTRIBUTE, pending)


def clear_service_secret(owner: Any, kind: str, *, user: Any = None) -> None:
    """Clear only the selected backend's reference and pending intent."""
    reference_field, _credential_type, _material_field = _SLOTS[kind]
    reference = getattr(owner, reference_field, None)
    if reference is not None:
        _remove_service_assignment(owner.service, reference, user=user)
    setattr(owner, reference_field, None)
    pending = dict(getattr(owner, _PENDING_ATTRIBUTE, {}))
    pending.pop(kind, None)
    setattr(owner, _PENDING_ATTRIBUTE, pending)


def _remove_service_assignment(service: Any, reference: Any, *, user: Any) -> None:
    """Authorize and remove one service assignment without deleting material."""
    if not is_netbox_openbao_installed():
        raise ValidationError(
            "Service SSH credential selects OpenBao, but netbox-openbao is not enabled."
        )
    from django.contrib.contenttypes.models import ContentType
    from netbox_openbao.models import CredentialAssignment
    from netbox_proxbox.integrations.openbao_assignments import (
        _require_scope,
        fresh_material_actor,
    )

    actor = fresh_material_actor(_require_actor(user))
    content_type = ContentType.objects.get_for_model(service)
    assignments = CredentialAssignment.objects.filter(
        credential__uuid=reference,
        assigned_object_type=content_type,
        assigned_object_id=service.pk,
        purpose="console",
    )
    for assignment in assignments.order_by("pk"):
        _require_scope(assignment, actor, "delete")
        assignment.delete()


def resolve_service_secret(owner: Any, kind: str, *, user: Any = None) -> str:
    """Reveal one OpenBao service secret with no Fernet fallback."""
    if not is_netbox_openbao_installed():
        raise ValidationError(
            "Service SSH credential selects OpenBao, but netbox-openbao is not enabled."
        )
    reference_field, credential_type, material_field = _SLOTS[kind]
    reference = getattr(owner, reference_field, None)
    if reference is None:
        raise ValidationError(
            "The service SSH credential reference cannot be resolved."
        )
    from django.apps import apps
    from django.contrib.contenttypes.models import ContentType

    try:
        actor = _require_actor(user)
        credential_model = apps.get_model("netbox_openbao", "Credential")
        assignment_model = apps.get_model("netbox_openbao", "CredentialAssignment")
        credential = (
            credential_model.objects.restrict(actor, "reveal")
            .filter(uuid=reference, credential_type=credential_type)
            .first()
        )
        if credential is None:
            raise ValidationError
        assigned = assignment_model.objects.filter(
            credential=credential,
            assigned_object_type=ContentType.objects.get_for_model(owner.service),
            assigned_object_id=owner.service_id,
            purpose="console",
            enabled=True,
        ).exists()
        if not assigned:
            raise ValidationError
        material = reveal_credential_material(credential, user=actor)
        value = material.get(material_field) if isinstance(material, dict) else None
        if not isinstance(value, str) or not value:
            raise ValidationError
        return value
    except PermissionDenied:
        raise
    except Exception:  # noqa: BLE001 - provider details must remain secret-safe
        raise ValidationError(
            "The service SSH credential reference cannot be resolved."
        ) from None


def _require_actor(user: Any) -> Any:
    if user is None or not getattr(user, "is_authenticated", False):
        raise PermissionDenied("Authenticated OpenBao credential access is required.")
    if not getattr(user, "is_active", False):
        raise PermissionDenied("An active OpenBao credential actor is required.")
    return user


def _save_assignment(service: Any, credential: Any, actor: Any) -> None:
    from django.contrib.contenttypes.models import ContentType
    from netbox_openbao.models import CredentialAssignment

    if not actor.has_perm("netbox_openbao.add_credentialassignment"):
        raise PermissionDenied(
            "Creating a service credential assignment requires add permission."
        )
    content_type = ContentType.objects.get_for_model(service)
    from netbox_proxbox.integrations.openbao_assignments import _require_scope

    primaries = (
        CredentialAssignment.objects.select_for_update()
        .filter(
            assigned_object_type=content_type,
            assigned_object_id=service.pk,
            purpose="console",
            is_primary=True,
        )
        .exclude(credential=credential)
    )
    for primary in primaries.order_by("pk"):
        _require_scope(primary, actor, "change")
        primary.is_primary = False
        primary.full_clean()
        primary.save(update_fields=["is_primary"])
    assignment = CredentialAssignment.objects.filter(
        credential=credential,
        assigned_object_type=content_type,
        assigned_object_id=service.pk,
        purpose="console",
    ).first()
    if assignment is None:
        assignment = CredentialAssignment(
            credential=credential,
            assigned_object_type=content_type,
            assigned_object_id=service.pk,
            purpose="console",
            is_primary=True,
        )
        assignment.full_clean()
        assignment.save()
    if not getattr(assignment, "enabled", True):
        raise ValidationError("A disabled credential assignment cannot be reused.")
    if not assignment.is_primary:
        if assignment.pk:
            _require_scope(assignment, actor, "change")
        assignment.is_primary = True
        assignment.full_clean()
        assignment.save(update_fields=["is_primary"])


def assign_existing_service_credential(
    owner: Any, service: Any, credential: Any, *, user: Any
) -> None:
    """Bind one authorized existing SSH credential as the service primary."""
    if not is_netbox_openbao_installed():
        raise ValidationError(
            "Service SSH credential selects OpenBao, but netbox-openbao is not enabled."
        )
    actor = _require_actor(user)
    from django.apps import apps

    credential_model = apps.get_model("netbox_openbao", "Credential")
    credential = (
        credential_model.objects.restrict(actor, "reveal")
        .filter(pk=getattr(credential, "pk", None))
        .first()
    )
    if credential is None:
        raise PermissionDenied(
            "You do not have permission to reveal the selected OpenBao credential."
        )
    credential_type = str(getattr(credential, "credential_type", ""))
    kinds = {
        "ssh-password": "password",
        "ssh-keypair": "private_key",
    }
    kind = kinds.get(credential_type)
    if kind is None:
        raise ValidationError("Select an SSH password or SSH key-pair credential.")
    from netbox_proxbox.integrations.openbao_assignments import _require_scope

    _require_scope(credential, actor, "reveal")
    _save_assignment(service, credential, actor)
    reference_field, _expected, _material = _SLOTS[kind]
    setattr(owner, reference_field, credential.uuid)
    other = "private_key" if kind == "password" else "password"
    setattr(owner, _SLOTS[other][0], None)


def ensure_active_service_assignment(owner: Any, *, user: Any) -> None:
    """Make the reference selected by ``auth_method`` the service primary."""
    if not is_netbox_openbao_installed():
        raise ValidationError(
            "Service SSH credential selects OpenBao, but netbox-openbao is not enabled."
        )
    kind = "private_key" if owner.auth_method == "key" else "password"
    reference_field, credential_type, _material_field = _SLOTS[kind]
    reference = getattr(owner, reference_field, None)
    if reference is None:
        return
    from django.apps import apps

    credential_model = apps.get_model("netbox_openbao", "Credential")
    actor = _require_actor(user)
    credential = (
        credential_model.objects.restrict(actor, "reveal")
        .filter(uuid=reference, credential_type=credential_type)
        .first()
    )
    if credential is None:
        raise ValidationError("The active service credential reference is invalid.")
    from netbox_proxbox.integrations.openbao_assignments import _require_scope

    _require_scope(credential, actor, "reveal")
    _save_assignment(owner.service, credential, actor)


@sensitive_variables()
def persist_service_material(owner: Any, service: Any, *, user: Any) -> None:
    """Write queued material inside the request-owned provider transaction."""
    pending = owner.__dict__.pop(_PENDING_ATTRIBUTE, {})
    if not pending:
        owner.save()
        return
    if not is_netbox_openbao_installed():
        raise ValidationError(
            "Service SSH credential selects OpenBao, but netbox-openbao is not enabled."
        )
    from netbox_proxbox.integrations.openbao_assignments import fresh_material_actor

    actor = fresh_material_actor(_require_actor(user))
    if not actor.has_perm("netbox_openbao.add_credential"):
        raise PermissionDenied(
            "Creating service SSH material requires OpenBao credential add permission."
        )
    locked_owner, locked_service = _lock_service_material_graph(owner, service)
    expected = getattr(
        owner, "_openbao_expected_references", _service_references(owner)
    )
    if _service_references(locked_owner) != tuple(expected):
        raise ValidationError(
            "The service credential changed before material persistence."
        )
    for kind, (plaintext, _queued_user, request) in _ordered_pending_items(
        owner, pending
    ):
        credential = _create_credential(
            locked_owner,
            locked_service,
            kind,
            plaintext,
            actor=actor,
            request=request,
        )
        setattr(locked_owner, _SLOTS[kind][0], credential.uuid)
        _save_assignment(locked_service, credential, actor)
    ensure_active_service_assignment(locked_owner, user=actor)
    locked_owner.save()
    for field_name, _credential_type, _material_field in _SLOTS.values():
        setattr(owner, field_name, getattr(locked_owner, field_name))


def _ordered_pending_items(owner: Any, pending: dict[str, tuple]) -> list[tuple]:
    """Persist the selected authentication secret last so it remains primary."""
    selected = "private_key" if owner.auth_method == "key" else "password"
    return sorted(pending.items(), key=lambda item: item[0] == selected)


def _lock_service_material_graph(owner: Any, service: Any) -> tuple[Any, Any]:
    """Lock settings, owner rows, provider policy, credentials, and assignments."""
    from django.contrib.contenttypes.models import ContentType
    from netbox_openbao.models import CredentialAssignment
    from netbox_openbao.synchronization import lock_material_subjects
    from netbox_proxbox.models import ProxmoxEndpointService, ServiceSSHCredential
    from .openbao_transaction import current_endpoint_material_context

    context = current_endpoint_material_context()
    if context is None:
        raise ValidationError(
            "OpenBao service material requires the outer request transaction."
        )
    settings = context.settings
    locked_service = ProxmoxEndpointService.objects.select_for_update().get(
        pk=service.pk
    )
    locked_owner = ServiceSSHCredential.objects.select_for_update().get(pk=owner.pk)
    from netbox_proxbox.integrations.openbao import validate_locked_openbao_storage

    validate_locked_openbao_storage(
        settings,
        endpoint_override=locked_owner.storage_backend,
        conflict_message="The service credential storage selection changed.",
    )
    policy = _default_policy()
    lock_material_subjects([], additional_policy_ids={policy.pk})
    content_type = ContentType.objects.get_for_model(service)
    list(
        CredentialAssignment.objects.select_for_update()
        .filter(
            assigned_object_type=content_type,
            assigned_object_id=service.pk,
            purpose="console",
        )
        .order_by("pk")
    )
    return locked_owner, locked_service


@sensitive_variables()
def _create_credential(
    owner: Any,
    service: Any,
    kind: str,
    plaintext: str,
    *,
    actor: Any,
    request: Any,
) -> Any:
    from netbox_openbao.choices import AccessActionChoices
    from netbox_openbao.models import Credential
    from netbox_openbao.services import enforce_policy_access, store_credential

    reference_field, credential_type, material_field = _SLOTS[kind]
    policy = _default_policy()
    credential = Credential(
        name=_credential_name(service, "console"),
        credential_type=credential_type,
        policy=policy,
        engine=policy.engine,
    )
    enforce_policy_access(credential, actor)

    def persist(metadata: dict[str, Any]) -> Any:
        for name, value in metadata.items():
            setattr(credential, name, value)
        credential.full_clean()
        credential.save()
        return credential

    stored, _version = store_credential(
        persist,
        credential_type,
        {material_field: plaintext},
        cas=0,
        user=actor,
        request=request,
        subject=credential,
        action=AccessActionChoices.ACTION_WRITE,
        prelocked=True,
    )
    if getattr(owner, reference_field, None):
        raise ValidationError(
            "The service credential changed during material creation."
        )
    return stored


def _service_assignments(service: Any) -> Any:
    from django.contrib.contenttypes.models import ContentType
    from netbox_openbao.models import CredentialAssignment

    return CredentialAssignment.objects.filter(
        assigned_object_type=ContentType.objects.get_for_model(service),
        assigned_object_id=service.pk,
        purpose="console",
    )


def service_has_openbao_state(service: Any) -> bool:
    """Return whether a service owns provider references or assignments."""
    try:
        owner = service.ssh_credential
    except (AttributeError, ObjectDoesNotExist):
        owner = None
    if owner is not None and any(_service_references(owner)):
        return True
    if not is_netbox_openbao_installed() or getattr(service, "pk", None) is None:
        return False
    return _service_assignments(service).exists()


def _service_requires_provider(service: Any) -> bool:
    try:
        owner = service.ssh_credential
    except (AttributeError, ObjectDoesNotExist):
        return False
    return owner.storage_backend == "openbao" or any(_service_references(owner))


@contextmanager
def service_cleanup_boundary(
    services: list[Any], *, actor: Any, request: Any = None
) -> Iterator[None]:
    """Own provider cleanup before framework deletion transactions begin."""
    actor = _require_actor(actor)
    if request is not None:
        request.sensitive_post_parameters = "__ALL__"
    provider_services = [
        service for service in services if _service_requires_provider(service)
    ]
    if not provider_services:
        from django.db import transaction

        with transaction.atomic():
            yield
        return
    if not is_netbox_openbao_installed():
        raise ValidationError(
            "OpenBao service references remain. Restore netbox-openbao before deletion."
        )
    from .openbao_transaction import endpoint_material_transaction

    endpoints = list(
        {service.endpoint_id: service.endpoint for service in services}.values()
    )
    with endpoint_material_transaction(endpoints):
        yield


@contextmanager
def endpoint_service_cleanup_boundary(
    endpoints: list[Any], *, actor: Any, request: Any = None
) -> Iterator[None]:
    """Own endpoint and child-service cleanup in one provider transaction."""
    actor = _require_actor(actor)
    services = [
        service
        for endpoint in endpoints
        for service in endpoint.application_services.select_related("ssh_credential")
    ]
    from netbox_proxbox.integrations.openbao import (
        endpoint_holds_openbao_references,
        endpoint_uses_openbao_storage,
    )

    needs_provider = any(
        endpoint_holds_openbao_references(endpoint)
        or endpoint_uses_openbao_storage(endpoint)
        for endpoint in endpoints
    ) or any(_service_requires_provider(service) for service in services)
    if request is not None:
        request.sensitive_post_parameters = "__ALL__"
    if not needs_provider:
        from django.db import transaction

        with transaction.atomic():
            yield
        return
    if not is_netbox_openbao_installed():
        raise ValidationError(
            "OpenBao references remain. Restore netbox-openbao before deletion."
        )
    from .openbao_transaction import endpoint_material_transaction

    for endpoint in endpoints:
        endpoint._openbao_actor_user = actor
    with endpoint_material_transaction(endpoints):
        yield


def cleanup_service_assignments(service: Any, *, actor: Any) -> None:
    """Delete authorized service assignments without deleting shared credentials."""
    if not is_netbox_openbao_installed():
        return
    from netbox_proxbox.integrations.openbao_assignments import (
        _require_scope,
        fresh_material_actor,
    )

    fresh_actor = fresh_material_actor(_require_actor(actor))
    assignments = list(_service_assignments(service).select_for_update().order_by("pk"))
    for assignment in assignments:
        _require_scope(assignment, fresh_actor, "delete")
    _service_assignments(service).filter(
        pk__in=[assignment.pk for assignment in assignments]
    ).delete()


def cleanup_service_credential(owner: Any, *, actor: Any) -> None:
    """Clear one owner's references and every console assignment on its service."""
    cleanup_service_assignments(owner.service, actor=actor)
    for field_name, _credential_type, _material_field in _SLOTS.values():
        setattr(owner, field_name, None)
    if owner.pk is not None:
        owner.save(update_fields=[slot[0] for slot in _SLOTS.values()])


def cleanup_service_state(service: Any, *, actor: Any) -> None:
    """Clear every provider-owned relation for one application service."""
    try:
        owner = service.ssh_credential
    except (AttributeError, ObjectDoesNotExist):
        cleanup_service_assignments(service, actor=actor)
    else:
        cleanup_service_credential(owner, actor=actor)


def cleanup_endpoint_services(endpoint: Any, *, actor: Any) -> None:
    """Clear provider state for every service before an endpoint cascade."""
    services = list(
        endpoint.application_services.select_related("ssh_credential").order_by("pk")
    )
    for service in services:
        cleanup_service_state(service, actor=actor)


def _guard_service_delete(sender: type, instance: Any, **_kwargs: Any) -> None:
    """Refuse raw deletes and cascades while provider-owned state remains."""
    from netbox_proxbox.models import (
        ProxmoxEndpoint,
        ProxmoxEndpointService,
        ServiceSSHCredential,
    )

    if sender is ServiceSSHCredential and any(_service_references(instance)):
        raise ValidationError(
            "OpenBao service credential references remain. Use the supported cleanup path."
        )
    if sender is ServiceSSHCredential and is_netbox_openbao_installed():
        if _service_assignments(instance.service).exists():
            raise ValidationError(
                "OpenBao service assignments remain. Use the supported cleanup path."
            )
    if sender is ProxmoxEndpointService and service_has_openbao_state(instance):
        raise ValidationError(
            "OpenBao service state remains. Use the supported cleanup path."
        )
    if sender is ProxmoxEndpoint:
        services = instance.application_services.select_related("ssh_credential")
        if any(service_has_openbao_state(service) for service in services):
            raise ValidationError(
                "OpenBao service state remains. Use the supported endpoint cleanup path."
            )


def install_service_material_guards() -> None:
    """Install fail-closed guards for raw service and parent deletion."""
    from django.db.models.signals import pre_delete
    from netbox_proxbox.models import (
        ProxmoxEndpoint,
        ProxmoxEndpointService,
        ServiceSSHCredential,
    )

    for model in (ServiceSSHCredential, ProxmoxEndpointService, ProxmoxEndpoint):
        pre_delete.connect(
            _guard_service_delete,
            sender=model,
            weak=False,
            dispatch_uid=f"proxbox_openbao_service_delete_guard_{model._meta.label_lower}",
        )
