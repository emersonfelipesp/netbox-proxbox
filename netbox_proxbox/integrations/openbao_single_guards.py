"""Fail-closed ORM and downgrade guards for one-secret owners."""

from __future__ import annotations

from collections.abc import Iterable
from functools import wraps
from typing import Any, Callable

from django.core.exceptions import ValidationError
from django.db.models.signals import pre_delete

from .openbao_single_pending import SPECS, spec_for

_CLEANUP = (
    "OpenBao references or assignments remain. Use the supported credential "
    "cleanup path before bulk mutation, deletion, or storage switching."
)


def _owner_has_state(owner: Any) -> bool:
    from .openbao_single_writer import _has_owned_assignments

    spec = spec_for(owner)
    return getattr(
        owner, spec.reference_field, None
    ) is not None or _has_owned_assignments(owner)


def _queryset_has_state(queryset: Any) -> bool:
    spec = spec_for(queryset.model)
    if queryset.filter(**{f"{spec.reference_field}__isnull": False}).exists():
        return True
    try:
        from netbox_openbao.models import CredentialAssignment
    except ImportError:
        return False
    owner_ids = queryset.values_list("pk", flat=True)
    return CredentialAssignment.objects.filter(
        assigned_object_type__app_label=queryset.model._meta.app_label,
        assigned_object_type__model=queryset.model._meta.model_name,
        assigned_object_id__in=owner_ids,
        purpose=spec.purpose,
    ).exists()


def _owner_models() -> tuple[type, ...]:
    from netbox_proxbox.models import (
        FastAPIEndpoint,
        FirecrackerHost,
        PBSEndpoint,
        PDMEndpoint,
    )

    return FastAPIEndpoint, PBSEndpoint, PDMEndpoint, FirecrackerHost


def _is_owner_model(model: type) -> bool:
    return model._meta.model_name in SPECS


def _guard_owner_update(queryset: Any, fields: set[str]) -> None:
    spec = spec_for(queryset.model)
    protected = {spec.reference_field, spec.encrypted_field}
    if fields.intersection(protected) or _queryset_has_state(queryset):
        raise ValidationError(_CLEANUP)


def _guard_settings_downgrade(value: Any) -> None:
    from netbox_proxbox.choices import CredentialStorageBackendChoices
    from .openbao import is_netbox_openbao_installed

    supported = {
        "",
        CredentialStorageBackendChoices.OPENBAO,
        CredentialStorageBackendChoices.LEGACY_ENCRYPTED,
    }
    if not isinstance(value, str) or value not in supported:
        raise ValidationError(_CLEANUP)
    backend = value
    if not backend:
        backend = (
            CredentialStorageBackendChoices.OPENBAO
            if is_netbox_openbao_installed()
            else CredentialStorageBackendChoices.LEGACY_ENCRYPTED
        )
    if backend == CredentialStorageBackendChoices.OPENBAO:
        return
    from .openbao_cloudinit_guards import any_cloudinit_openbao_state

    if any(_queryset_has_state(model.objects.all()) for model in _owner_models()):
        raise ValidationError(_CLEANUP)
    if any_cloudinit_openbao_state():
        raise ValidationError(_CLEANUP)


def _guard_update(queryset: Any, updates: dict[str, Any]) -> None:
    from netbox_proxbox.models import ProxboxPluginSettings

    if queryset.model._meta.label_lower == "netbox_proxbox.proxmoxvmcloudinit":
        from .openbao_cloudinit_guards import guard_cloudinit_update

        guard_cloudinit_update(queryset, set(updates))
        return

    if _is_owner_model(queryset.model):
        _guard_owner_update(queryset, set(updates))
    elif queryset.model is ProxboxPluginSettings:
        if "credential_storage_backend" in updates:
            _guard_settings_downgrade(updates["credential_storage_backend"])


def _guard_bulk(
    queryset: Any, objects: list[Any], fields: set[str], *, creating: bool
) -> None:
    from netbox_proxbox.models import ProxboxPluginSettings

    if queryset.model._meta.label_lower == "netbox_proxbox.proxmoxvmcloudinit":
        from .openbao_cloudinit_guards import guard_cloudinit_bulk

        guard_cloudinit_bulk(queryset, objects, fields)
        return

    if queryset.model is ProxboxPluginSettings:
        _guard_settings_bulk(objects, fields, creating=creating)
        return
    if not _is_owner_model(queryset.model):
        return
    spec = spec_for(queryset.model)
    proposed = _bulk_proposes_reference(objects, spec.reference_field)
    affected = _bulk_affects_state(queryset, objects)
    material_fields = {spec.reference_field, spec.encrypted_field}
    if proposed or fields.intersection(material_fields):
        raise ValidationError(_CLEANUP)
    if affected or (creating and proposed):
        raise ValidationError(_CLEANUP)


def _guard_settings_bulk(
    objects: list[Any], fields: set[str], *, creating: bool
) -> None:
    backend_field = "credential_storage_backend"
    if not creating and backend_field not in fields:
        return
    for settings in objects:
        _guard_settings_downgrade(getattr(settings, backend_field, None))


def _bulk_proposes_reference(objects: list[Any], reference_field: str) -> bool:
    """Return whether any bulk object supplies an OpenBao reference."""
    return any(getattr(owner, reference_field, None) is not None for owner in objects)


def _bulk_affects_state(queryset: Any, objects: list[Any]) -> bool:
    """Return whether bulk persistence would bypass an OpenBao-backed owner."""
    ids = [owner.pk for owner in objects if owner.pk is not None]
    if not ids:
        return False
    return _queryset_has_state(queryset.filter(pk__in=ids))


def _guard_delete(queryset: Any) -> None:
    if queryset.model._meta.label_lower == "netbox_proxbox.proxmoxvmcloudinit":
        from .openbao_cloudinit_guards import guard_cloudinit_delete

        guard_cloudinit_delete(queryset)
        return
    if _is_owner_model(queryset.model) and _queryset_has_state(queryset):
        raise ValidationError(_CLEANUP)


def _install_queryset_guards(queryset_type: type) -> None:
    if vars(queryset_type).get("_proxbox_single_secret_guards_installed", False):
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
        normalized = {str(field) for field in fields}
        _guard_bulk(queryset, materialized, normalized, creating=False)
        return original_bulk_update(
            queryset, materialized, tuple(normalized), *args, **kwargs
        )

    @wraps(original_bulk_create)
    def guarded_bulk_create(
        queryset: Any, objs: Iterable[Any], *args: Any, **kwargs: Any
    ) -> Any:
        materialized = list(objs)
        fields = {str(field) for field in (kwargs.get("update_fields") or ())}
        _guard_bulk(queryset, materialized, fields, creating=True)
        return original_bulk_create(queryset, materialized, *args, **kwargs)

    @wraps(original_delete)
    def guarded_delete(queryset: Any) -> Any:
        _guard_delete(queryset)
        return original_delete(queryset)

    @wraps(original_raw_delete)
    def guarded_raw_delete(queryset: Any, using: str) -> int:
        _guard_delete(queryset)
        return original_raw_delete(queryset, using)

    queryset_type.update = guarded_update
    queryset_type.bulk_update = guarded_bulk_update
    queryset_type.bulk_create = guarded_bulk_create
    queryset_type.delete = guarded_delete
    queryset_type._raw_delete = guarded_raw_delete
    queryset_type._proxbox_single_secret_guards_installed = True


def _guard_settings_save(original: Callable) -> Callable:
    @wraps(original)
    def guarded(instance: Any, *args: Any, **kwargs: Any) -> Any:
        _guard_settings_downgrade(instance.credential_storage_backend)
        return original(instance, *args, **kwargs)

    return guarded


def _guard_parent_delete(sender: type, instance: Any, **_kwargs: Any) -> None:
    from netbox_proxbox.models import FirecrackerHostPool

    if _is_owner_model(sender) and _owner_has_state(instance):
        raise ValidationError(_CLEANUP)
    if sender is FirecrackerHostPool and _queryset_has_state(instance.hosts.all()):
        raise ValidationError(_CLEANUP)


def install_single_secret_material_guards() -> None:
    """Install raw, bulk, cascade, and storage-downgrade guards."""
    from netbox_proxbox.models import FirecrackerHostPool, ProxboxPluginSettings

    models = (*_owner_models(), FirecrackerHostPool, ProxboxPluginSettings)
    for queryset_type in {type(model._default_manager.all()) for model in models}:
        _install_queryset_guards(queryset_type)
    if not getattr(
        ProxboxPluginSettings.save, "_proxbox_single_secret_downgrade_guard", False
    ):
        ProxboxPluginSettings.save = _guard_settings_save(ProxboxPluginSettings.save)
        ProxboxPluginSettings.save._proxbox_single_secret_downgrade_guard = True
    for model in (*_owner_models(), FirecrackerHostPool):
        pre_delete.connect(
            _guard_parent_delete,
            sender=model,
            weak=False,
            dispatch_uid=f"proxbox_openbao_single_parent_guard_{model._meta.label_lower}",
        )
