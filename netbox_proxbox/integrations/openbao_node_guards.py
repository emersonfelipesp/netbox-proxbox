"""Fail-closed guards for node OpenBao references outside model save paths."""

from __future__ import annotations

from collections.abc import Iterable
from functools import wraps
from typing import Any, Callable

from django.core.exceptions import ValidationError
from django.db.models import Q
from django.db.models.signals import pre_delete

from .openbao_node_pending import SLOTS

_CLEANUP_MESSAGE = (
    "OpenBao node references or assignments remain. Use the supported node "
    "credential cleanup path before bulk mutation, deletion, or storage switching."
)
_PROVIDER_MESSAGE = (
    "OpenBao node references remain, but netbox-openbao is unavailable. Restore "
    "the provider and run the supported cleanup path before continuing."
)
_BACKEND_MISSING = object()


def _reference_filter(prefix: str = "") -> Q:
    query = Q()
    for name in SLOTS:
        query |= Q(**{f"{prefix}{name}__isnull": False})
    return query


def _provider_assignment_model() -> type:
    from .openbao import is_netbox_openbao_installed

    if not is_netbox_openbao_installed():
        raise ValidationError(_PROVIDER_MESSAGE)
    try:
        from netbox_openbao.models import CredentialAssignment
    except ImportError as exc:
        raise ValidationError(_PROVIDER_MESSAGE) from exc
    return CredentialAssignment


def _owner_scope(queryset: Any) -> Any:
    from netbox_proxbox.models import NodeSSHCredential

    return NodeSSHCredential.objects.filter(pk__in=queryset.values("pk"))


def _owners_have_state(queryset: Any) -> bool:
    owners = _owner_scope(queryset)
    if owners.filter(_reference_filter()).exists():
        return True
    device_ids = owners.exclude(node__netbox_device_id=None).values_list(
        "node__netbox_device_id", flat=True
    )
    if not device_ids.exists():
        return False
    try:
        assignments = _provider_assignment_model()
    except ValidationError:
        return False
    return assignments.objects.filter(
        assigned_object_type__app_label="dcim",
        assigned_object_type__model="device",
        assigned_object_id__in=device_ids,
        purpose="login",
    ).exists()


def _nodes_have_state(queryset: Any) -> bool:
    from netbox_proxbox.models import NodeSSHCredential

    owners = NodeSSHCredential.objects.filter(node_id__in=queryset.values("pk"))
    return _owners_have_state(owners)


def _endpoints_have_state(queryset: Any, *, inherited_only: bool = False) -> bool:
    from netbox_proxbox.models import NodeSSHCredential

    if inherited_only:
        queryset = queryset.filter(credential_storage_backend="")
    owners = NodeSSHCredential.objects.filter(
        node__endpoint_id__in=queryset.values("pk")
    )
    return _owners_have_state(owners)


def _device_has_state(device: Any) -> bool:
    from netbox_proxbox.models import NodeSSHCredential

    owners = NodeSSHCredential.objects.filter(node__netbox_device_id=device.pk)
    if _owners_have_state(owners):
        return True
    try:
        assignments = _provider_assignment_model()
    except ValidationError:
        return False
    return assignments.objects.filter(
        assigned_object_type__app_label="dcim",
        assigned_object_type__model="device",
        assigned_object_id=device.pk,
    ).exists()


def _raise_if_queryset_affected(queryset: Any) -> None:
    from netbox_proxbox.models import NodeSSHCredential, ProxmoxEndpoint, ProxmoxNode

    if queryset.model is NodeSSHCredential and _owners_have_state(queryset):
        raise ValidationError(_CLEANUP_MESSAGE)
    if queryset.model is ProxmoxNode and _nodes_have_state(queryset):
        raise ValidationError(_CLEANUP_MESSAGE)
    if queryset.model is ProxmoxEndpoint and _endpoints_have_state(queryset):
        raise ValidationError(_CLEANUP_MESSAGE)


def _update_keeps_openbao(value: Any) -> bool:
    """Return whether a literal backend update still resolves to OpenBao."""
    from netbox_proxbox.choices import CredentialStorageBackendChoices
    from netbox_proxbox.integrations.openbao import (
        effective_credential_storage_backend,
    )

    if value == CredentialStorageBackendChoices.OPENBAO:
        return True
    if value in (None, ""):
        return (
            effective_credential_storage_backend()
            == CredentialStorageBackendChoices.OPENBAO
        )
    return False


def _guard_update(queryset: Any, updates: dict[str, Any]) -> None:
    from netbox_proxbox.models import (
        NodeSSHCredential,
        ProxmoxEndpoint,
        ProxmoxNode,
        ProxboxPluginSettings,
    )

    fields = set(updates)
    if queryset.model is NodeSSHCredential:
        _guard_owner_update(queryset, fields)
    elif queryset.model is ProxmoxNode:
        _guard_node_update(queryset, fields)
    elif queryset.model is ProxmoxEndpoint:
        _guard_endpoint_update(queryset, updates)
    elif queryset.model is ProxboxPluginSettings:
        _guard_settings_update(updates)


def _guard_owner_update(queryset: Any, fields: set[str]) -> None:
    if fields.intersection(SLOTS) or _owners_have_state(queryset):
        raise ValidationError(_CLEANUP_MESSAGE)


def _guard_node_update(queryset: Any, fields: set[str]) -> None:
    watched = {"endpoint", "endpoint_id", "netbox_device", "netbox_device_id"}
    if fields.intersection(watched):
        _raise_if_queryset_affected(queryset)


def _guard_endpoint_update(queryset: Any, updates: dict[str, Any]) -> None:
    backend = updates.get("credential_storage_backend", _BACKEND_MISSING)
    if backend is _BACKEND_MISSING or _update_keeps_openbao(backend):
        return
    _raise_if_queryset_affected(queryset)


def _guard_settings_update(updates: dict[str, Any]) -> None:
    from netbox_proxbox.models import ProxmoxEndpoint

    backend = updates.get("credential_storage_backend", _BACKEND_MISSING)
    if backend is _BACKEND_MISSING or _update_keeps_openbao(backend):
        return
    inherited = ProxmoxEndpoint.objects.filter(credential_storage_backend="")
    if _endpoints_have_state(inherited):
        raise ValidationError(_CLEANUP_MESSAGE)


def _guard_bulk_objects(queryset: Any, objects: list[Any], fields: set[str]) -> None:
    from netbox_proxbox.models import NodeSSHCredential

    if queryset.model is not NodeSSHCredential:
        _guard_non_owner_bulk(queryset, objects, fields)
        return
    proposed_references = any(
        getattr(obj, name, None) is not None for obj in objects for name in SLOTS
    )
    pks = [obj.pk for obj in objects if obj.pk is not None]
    affected = bool(pks) and _owners_have_state(queryset.filter(pk__in=pks))
    if proposed_references or fields.intersection(SLOTS) or affected:
        raise ValidationError(_CLEANUP_MESSAGE)


def _guard_non_owner_bulk(
    queryset: Any,
    objects: list[Any],
    fields: set[str],
) -> None:
    if not fields:
        return
    pks = [obj.pk for obj in objects if obj.pk is not None]
    updates = (
        {name: getattr(objects[0], name, None) for name in fields} if objects else {}
    )
    if "credential_storage_backend" in fields and any(
        not _update_keeps_openbao(obj.credential_storage_backend) for obj in objects
    ):
        updates["credential_storage_backend"] = "legacy_encrypted"
    _guard_update(queryset.filter(pk__in=pks), updates)


def _install_queryset_guards(queryset_type: type) -> None:
    if vars(queryset_type).get("_proxbox_node_openbao_guards_installed", False):
        return
    original_update = queryset_type.update
    original_bulk_update = queryset_type.bulk_update
    original_bulk_create = queryset_type.bulk_create
    original_delete = queryset_type.delete
    original_raw_delete = queryset_type._raw_delete

    @wraps(original_update)
    def guarded_update(queryset: Any, **updates: Any) -> int:
        _guard_update(queryset, updates)
        return original_update(queryset, **updates)

    @wraps(original_bulk_update)
    def guarded_bulk_update(
        queryset: Any,
        objs: Iterable[Any],
        fields: Iterable[str],
        *args: Any,
        **kwargs: Any,
    ) -> int:
        materialized = list(objs)
        normalized = {str(name) for name in fields}
        _guard_bulk_objects(queryset, materialized, normalized)
        return original_bulk_update(
            queryset, materialized, tuple(normalized), *args, **kwargs
        )

    @wraps(original_bulk_create)
    def guarded_bulk_create(
        queryset: Any,
        objs: Iterable[Any],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        materialized = list(objs)
        fields = {str(name) for name in (kwargs.get("update_fields") or ())}
        _guard_bulk_objects(queryset, materialized, fields)
        return original_bulk_create(queryset, materialized, *args, **kwargs)

    @wraps(original_delete)
    def guarded_delete(queryset: Any) -> Any:
        _raise_if_queryset_affected(queryset)
        return original_delete(queryset)

    @wraps(original_raw_delete)
    def guarded_raw_delete(queryset: Any, using: str) -> int:
        _raise_if_queryset_affected(queryset)
        return original_raw_delete(queryset, using)

    queryset_type.update = guarded_update
    queryset_type.bulk_update = guarded_bulk_update
    queryset_type.bulk_create = guarded_bulk_create
    queryset_type.delete = guarded_delete
    queryset_type._raw_delete = guarded_raw_delete
    queryset_type._proxbox_node_openbao_guards_installed = True


def _guard_endpoint_save(original: Callable) -> Callable:
    @wraps(original)
    def guarded(instance: Any, *args: Any, **kwargs: Any) -> Any:
        from netbox_proxbox.integrations.openbao import (
            CredentialStorageBackendChoices,
            effective_credential_storage_backend,
        )

        backend = effective_credential_storage_backend(instance)
        queryset = type(instance).objects.filter(pk=instance.pk)
        if (
            instance.pk is not None
            and backend != CredentialStorageBackendChoices.OPENBAO
            and _endpoints_have_state(queryset)
        ):
            raise ValidationError(_CLEANUP_MESSAGE)
        return original(instance, *args, **kwargs)

    return guarded


def _guard_settings_save(original: Callable) -> Callable:
    @wraps(original)
    def guarded(instance: Any, *args: Any, **kwargs: Any) -> Any:
        from netbox_proxbox.choices import CredentialStorageBackendChoices
        from netbox_proxbox.integrations.openbao import (
            is_netbox_openbao_installed,
        )
        from netbox_proxbox.models import ProxmoxEndpoint

        backend = instance.credential_storage_backend or (
            CredentialStorageBackendChoices.OPENBAO
            if is_netbox_openbao_installed()
            else CredentialStorageBackendChoices.LEGACY_ENCRYPTED
        )
        inherited = ProxmoxEndpoint.objects.filter(credential_storage_backend="")
        if backend != CredentialStorageBackendChoices.OPENBAO and _endpoints_have_state(
            inherited
        ):
            raise ValidationError(_CLEANUP_MESSAGE)
        return original(instance, *args, **kwargs)

    return guarded


def _guard_parent_delete(sender: type, instance: Any, **_kwargs: Any) -> None:
    from dcim.models import Device
    from netbox_proxbox.models import ProxmoxEndpoint, ProxmoxNode

    if sender is Device and _device_has_state(instance):
        raise ValidationError(_CLEANUP_MESSAGE)
    if sender is ProxmoxNode and _nodes_have_state(
        sender.objects.filter(pk=instance.pk)
    ):
        raise ValidationError(_CLEANUP_MESSAGE)
    if sender is ProxmoxEndpoint and _endpoints_have_state(
        sender.objects.filter(pk=instance.pk)
    ):
        raise ValidationError(_CLEANUP_MESSAGE)


def install_node_material_guards() -> None:
    """Install bulk, raw-delete, parent-cascade, and downgrade guards."""
    from dcim.models import Device
    from netbox_proxbox.models import (
        NodeSSHCredential,
        ProxmoxEndpoint,
        ProxmoxNode,
        ProxboxPluginSettings,
    )

    queryset_types = {
        type(model._default_manager.all())
        for model in (
            NodeSSHCredential,
            ProxmoxNode,
            ProxmoxEndpoint,
            ProxboxPluginSettings,
        )
    }
    for queryset_type in queryset_types:
        _install_queryset_guards(queryset_type)
    if not getattr(ProxmoxEndpoint.save, "_proxbox_node_downgrade_guard", False):
        ProxmoxEndpoint.save = _guard_endpoint_save(ProxmoxEndpoint.save)
        ProxmoxEndpoint.save._proxbox_node_downgrade_guard = True
    if not getattr(ProxboxPluginSettings.save, "_proxbox_node_downgrade_guard", False):
        ProxboxPluginSettings.save = _guard_settings_save(ProxboxPluginSettings.save)
        ProxboxPluginSettings.save._proxbox_node_downgrade_guard = True
    for model in (Device, ProxmoxNode, ProxmoxEndpoint):
        pre_delete.connect(
            _guard_parent_delete,
            sender=model,
            weak=False,
            dispatch_uid=f"proxbox_openbao_node_parent_guard_{model._meta.label_lower}",
        )
