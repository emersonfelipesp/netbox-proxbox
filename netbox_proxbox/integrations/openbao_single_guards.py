"""Fail-closed ORM and downgrade guards for one-secret owners."""

from __future__ import annotations

from collections.abc import Iterable
from contextvars import ContextVar
from functools import wraps
from typing import Any, Callable

from django.core.exceptions import ValidationError
from django.db import IntegrityError, router, transaction
from django.db.models.signals import pre_delete

from .openbao_single_pending import SPECS, spec_for

_CLEANUP = (
    "OpenBao references or assignments remain. Use the supported credential "
    "cleanup path before bulk mutation, deletion, or storage switching."
)
_CONFLICT_UPSERT = (
    "Conflict upserts cannot change credential_storage_backend. Use supported "
    "save(), update(), or bulk_update() storage persistence instead."
)
_VALIDATED_SETTINGS_BULK_ALIASES: ContextVar[frozenset[str]] = ContextVar(
    "proxbox_validated_settings_bulk_aliases",
    default=frozenset(),
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
    from .openbao import is_netbox_openbao_installed

    if not is_netbox_openbao_installed():
        return False
    try:
        from netbox_openbao.models import CredentialAssignment
    except ImportError:
        return False
    owner_ids = queryset.values_list("pk", flat=True)
    return (
        CredentialAssignment.objects.using(queryset.db)
        .filter(
            assigned_object_type__app_label=queryset.model._meta.app_label,
            assigned_object_type__model=queryset.model._meta.model_name,
            assigned_object_id__in=owner_ids,
            purpose=spec.purpose,
        )
        .exists()
    )


def _owner_models() -> tuple[type, ...]:
    from netbox_proxbox.models import (
        FastAPIEndpoint,
        FirecrackerHost,
        PBSEndpoint,
        PDMEndpoint,
    )

    return FastAPIEndpoint, PBSEndpoint, PDMEndpoint, FirecrackerHost


def _is_owner_model(model: type) -> bool:
    return model in _owner_models()


def _guard_owner_update(queryset: Any, updates: dict[str, Any]) -> None:
    spec = spec_for(queryset.model)
    fields = set(updates)
    if spec.reference_field in fields:
        raise ValidationError(_CLEANUP)
    if spec.encrypted_field in fields:
        from netbox_proxbox.services.encryption_recovery import (
            _encrypted_queryset_write_permit_matches,
        )

        if _encrypted_queryset_write_permit_matches(queryset, updates):
            return
        raise ValidationError(_CLEANUP)
    if _queryset_has_state(queryset):
        raise ValidationError(_CLEANUP)


def _guard_settings_downgrade(value: Any, *, using: str = "default") -> None:
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

    if any(
        _queryset_has_state(model.objects.using(using).all())
        for model in _owner_models()
    ):
        raise ValidationError(_CLEANUP)
    if any_cloudinit_openbao_state(using=using) or _inherited_endpoints_have_state(
        using=using
    ):
        raise ValidationError(_CLEANUP)


def _guard_all_settings_state(value: Any, *, using: str) -> None:
    """Run every plugin-wide storage guard while the settings row is locked."""
    from .openbao_node_guards import _guard_settings_update

    _guard_settings_downgrade(value, using=using)
    _guard_settings_update({"credential_storage_backend": value}, using=using)


def _lock_settings_singleton(using: str, *, required: bool = True) -> bool:
    """Lock the singleton before inspecting any provider-owned state.

    A provider material owner must already have been entered in autocommit;
    inside its durable transaction, this is the first row lock. Settings-only
    writers instead open their own atomic block before calling this helper.
    Every owner, assignment, or credential lock follows this singleton lock,
    while downstream row order varies by transaction family. Keeping the
    downgrade path first prevents check-then-save races and deadlocks.

    ``required=False`` is only for a settings save that carries an explicit
    primary key: it returns ``False`` when no singleton exists yet, so the
    caller can persist the first row as an insert-only write.
    """
    from netbox_proxbox.models import ProxboxPluginSettings

    singleton = ProxboxPluginSettings.objects.using(using).select_for_update()
    if required:
        singleton.get(singleton_key="default")
        return True
    return bool(list(singleton.filter(singleton_key="default")[:1]))


def _locked_settings_write(using: str, values: list[Any], write: Callable) -> Any:
    """Serialize final storage guards and one settings persistence operation."""
    with transaction.atomic(using=using):
        _lock_settings_singleton(using)
        for value in values:
            _guard_all_settings_state(value, using=using)
        return write()


def _inherited_endpoints_have_state(*, using: str = "default") -> bool:
    """Return whether endpoints that inherit the plugin backend hold OpenBao state."""
    from django.db.models import Q
    from netbox_proxbox.models import ProxmoxEndpoint

    from .openbao import is_netbox_openbao_installed

    inherited = ProxmoxEndpoint.objects.using(using).filter(
        credential_storage_backend=""
    )
    referenced = Q()
    for field in ProxmoxEndpoint._meta.concrete_fields:
        if field.name.startswith("openbao_") and field.name.endswith(
            "_credential_uuid"
        ):
            referenced |= Q(**{f"{field.name}__isnull": False})
    if inherited.filter(referenced).exists():
        return True
    if not is_netbox_openbao_installed():
        return False
    from netbox_openbao.models import CredentialAssignment

    return (
        CredentialAssignment.objects.using(using)
        .filter(
            assigned_object_type__app_label=ProxmoxEndpoint._meta.app_label,
            assigned_object_type__model=ProxmoxEndpoint._meta.model_name,
            assigned_object_id__in=inherited.values("pk"),
        )
        .exists()
    )


def _guard_update(queryset: Any, updates: dict[str, Any]) -> None:
    from netbox_proxbox.models import ProxboxPluginSettings, ProxmoxVMCloudInit

    if queryset.model is ProxmoxVMCloudInit:
        from .openbao_cloudinit_guards import guard_cloudinit_update

        guard_cloudinit_update(queryset, set(updates))
        return

    if _is_owner_model(queryset.model):
        _guard_owner_update(queryset, updates)
    elif queryset.model is ProxboxPluginSettings:
        return


def _guard_bulk(
    queryset: Any, objects: list[Any], fields: set[str], *, creating: bool
) -> None:
    from netbox_proxbox.models import ProxboxPluginSettings, ProxmoxVMCloudInit

    if queryset.model is ProxmoxVMCloudInit:
        from .openbao_cloudinit_guards import guard_cloudinit_bulk

        guard_cloudinit_bulk(queryset, objects, fields)
        return

    if queryset.model is ProxboxPluginSettings:
        _guard_settings_bulk(
            objects,
            fields,
            creating=creating,
            using=queryset.db,
        )
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
    objects: list[Any], fields: set[str], *, creating: bool, using: str
) -> None:
    backend_field = "credential_storage_backend"
    if not creating and backend_field not in fields:
        return
    for settings in objects:
        _guard_settings_downgrade(
            getattr(settings, backend_field, None),
            using=using,
        )


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
    from netbox_proxbox.models import ProxmoxVMCloudInit

    if queryset.model is ProxmoxVMCloudInit:
        from .openbao_cloudinit_guards import guard_cloudinit_delete

        guard_cloudinit_delete(queryset)
        return
    if _is_owner_model(queryset.model) and _queryset_has_state(queryset):
        raise ValidationError(_CLEANUP)


def _bulk_create_option(
    args: tuple[Any, ...], kwargs: dict[str, Any], name: str, position: int
) -> Any:
    if name in kwargs:
        return kwargs[name]
    return args[position] if len(args) > position else None


def _reject_settings_storage_conflict_upsert(
    queryset: Any, args: tuple[Any, ...], kwargs: dict[str, Any]
) -> None:
    from netbox_proxbox.models import ProxboxPluginSettings

    if queryset.model is not ProxboxPluginSettings:
        return
    update_conflicts = _bulk_create_option(args, kwargs, "update_conflicts", 2)
    update_fields = _bulk_create_option(args, kwargs, "update_fields", 3) or ()
    if update_conflicts and "credential_storage_backend" in {
        str(field) for field in update_fields
    }:
        raise ValidationError(_CONFLICT_UPSERT)


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
        from netbox_proxbox.models import ProxboxPluginSettings

        queryset._for_write = True
        if (
            queryset.model is ProxboxPluginSettings
            and "credential_storage_backend" in updates
        ):
            if queryset.db in _VALIDATED_SETTINGS_BULK_ALIASES.get():
                return original_update(queryset, **updates)
            return _locked_settings_write(
                queryset.db,
                [updates["credential_storage_backend"]],
                lambda: original_update(queryset, **updates),
            )
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
        from netbox_proxbox.models import ProxboxPluginSettings

        queryset._for_write = True
        if (
            queryset.model is ProxboxPluginSettings
            and "credential_storage_backend" in normalized
        ):
            values = [
                getattr(obj, "credential_storage_backend", None) for obj in materialized
            ]

            def write_validated_bulk() -> int:
                aliases = _VALIDATED_SETTINGS_BULK_ALIASES.get()
                token = _VALIDATED_SETTINGS_BULK_ALIASES.set(aliases | {queryset.db})
                try:
                    return original_bulk_update(
                        queryset, materialized, tuple(normalized), *args, **kwargs
                    )
                finally:
                    _VALIDATED_SETTINGS_BULK_ALIASES.reset(token)

            return _locked_settings_write(queryset.db, values, write_validated_bulk)
        _guard_bulk(queryset, materialized, normalized, creating=False)
        return original_bulk_update(
            queryset, materialized, tuple(normalized), *args, **kwargs
        )

    @wraps(original_bulk_create)
    def guarded_bulk_create(
        queryset: Any, objs: Iterable[Any], *args: Any, **kwargs: Any
    ) -> Any:
        materialized = list(objs)
        queryset._for_write = True
        _reject_settings_storage_conflict_upsert(queryset, args, kwargs)
        update_fields = _bulk_create_option(args, kwargs, "update_fields", 3) or ()
        fields = {str(field) for field in update_fields}
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
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and "credential_storage_backend" not in {
            str(field) for field in update_fields
        }:
            return original(instance, *args, **kwargs)
        using_value = kwargs.get("using")
        using = (
            using_value
            if isinstance(using_value, str)
            else router.db_for_write(type(instance), instance=instance)
        )
        if instance.pk is None:
            _guard_all_settings_state(
                instance.credential_storage_backend,
                using=using,
            )
            return original(instance, *args, **kwargs)
        return _save_keyed_settings(instance, original, args, kwargs, using)

    return guarded


def _save_keyed_settings(
    instance: Any, original: Callable, args: tuple, kwargs: dict, using: str
) -> Any:
    """Persist a settings instance that already carries a primary key.

    An existing singleton is always locked before the final storage guards.
    Without one, the first row is written insert-only so a concurrent first
    save can never fall back to an unguarded UPDATE; losing that race retries
    through the strict singleton lock, which reruns every guard.
    """
    values = [instance.credential_storage_backend]

    def write() -> Any:
        return original(instance, *args, **kwargs)

    if args or kwargs.get("update_fields") is not None or kwargs.get("force_update"):
        return _locked_settings_write(using, values, write)
    with transaction.atomic(using=using):
        if _lock_settings_singleton(using, required=False):
            _guard_all_settings_state(values[0], using=using)
            return write()
    try:
        with transaction.atomic(using=using):
            _guard_all_settings_state(values[0], using=using)
            return original(instance, **{**kwargs, "force_insert": True})
    except IntegrityError:
        return _locked_settings_write(using, values, write)


def _guard_parent_delete(sender: type, instance: Any, **_kwargs: Any) -> None:
    from netbox_proxbox.models import FirecrackerHostPool

    if _is_owner_model(sender) and _owner_has_state(instance):
        raise ValidationError(_CLEANUP)
    if sender is FirecrackerHostPool and _queryset_has_state(instance.hosts.all()):
        raise ValidationError(_CLEANUP)


def install_single_secret_material_guards() -> None:
    """Install raw, bulk, cascade, and storage-downgrade guards."""
    from netbox_proxbox.models import (
        FirecrackerHostPool,
        ProxboxPluginSettings,
        ProxmoxVMCloudInit,
    )

    models = (
        *_owner_models(),
        FirecrackerHostPool,
        ProxboxPluginSettings,
        ProxmoxVMCloudInit,
    )
    queryset_types = {
        type(manager.all())
        for model in models
        for manager in (model._default_manager, model._base_manager)
    }
    for queryset_type in sorted(
        queryset_types,
        key=lambda candidate: len(candidate.__mro__),
        reverse=True,
    ):
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
