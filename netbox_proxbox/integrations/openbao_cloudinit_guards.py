"""Fail-closed raw, bulk, cascade, and downgrade cloud-init guards."""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError
from django.db.models.signals import pre_delete

from .openbao_cloudinit import SPECS, _has_owned_assignments, _references

_CLEANUP = (
    "OpenBao cloud-init references or assignments remain. Use the supported "
    "credential cleanup path before bulk mutation, deletion, or storage switching."
)


def cloudinit_owner_has_state(owner: Any) -> bool:
    """Return whether one owner retains provider-owned state."""
    return any(_references(owner).values()) or _has_owned_assignments(owner)


def cloudinit_queryset_has_state(queryset: Any) -> bool:
    """Return whether any selected owner retains a provider reference."""
    query = None
    for spec in SPECS.values():
        branch = {f"{spec.reference_field}__isnull": False}
        query = (
            queryset.filter(**branch)
            if query is None
            else query | queryset.filter(**branch)
        )
    return bool(query is not None and query.exists())


def any_cloudinit_openbao_state() -> bool:
    """Return whether storage downgrade would strand cloud-init references."""
    from netbox_proxbox.models import ProxmoxVMCloudInit

    return cloudinit_queryset_has_state(ProxmoxVMCloudInit.objects.all())


def guard_cloudinit_update(queryset: Any, fields: set[str]) -> None:
    protected = {spec.reference_field for spec in SPECS.values()}
    if fields.intersection(protected) or cloudinit_queryset_has_state(queryset):
        raise ValidationError(_CLEANUP)


def guard_cloudinit_bulk(queryset: Any, objects: list[Any], fields: set[str]) -> None:
    protected = {spec.reference_field for spec in SPECS.values()}
    proposed = any(any(_references(owner).values()) for owner in objects)
    ids = [owner.pk for owner in objects if owner.pk is not None]
    affected = bool(ids) and cloudinit_queryset_has_state(queryset.filter(pk__in=ids))
    if proposed or affected or fields.intersection(protected):
        raise ValidationError(_CLEANUP)


def guard_cloudinit_delete(queryset: Any) -> None:
    """Refuse queryset deletion while provider references remain."""
    if cloudinit_queryset_has_state(queryset):
        raise ValidationError(_CLEANUP)


def _guard_parent_delete(sender: type, instance: Any, **_kwargs: Any) -> None:
    from netbox_proxbox.models import ProxmoxVMCloudInit
    from virtualization.models import VirtualMachine

    if sender is ProxmoxVMCloudInit and cloudinit_owner_has_state(instance):
        raise ValidationError(_CLEANUP)
    if sender is VirtualMachine:
        owner = ProxmoxVMCloudInit.objects.filter(virtual_machine=instance).first()
        if owner is not None and cloudinit_owner_has_state(owner):
            raise ValidationError(_CLEANUP)


def install_cloudinit_material_guards() -> None:
    """Install guards for every ORM path that bypasses model save/delete."""
    from netbox_proxbox.models import ProxmoxVMCloudInit
    from virtualization.models import VirtualMachine

    for model in (ProxmoxVMCloudInit, VirtualMachine):
        pre_delete.connect(
            _guard_parent_delete,
            sender=model,
            weak=False,
            dispatch_uid=f"proxbox_openbao_cloudinit_guard_{model._meta.label_lower}",
        )
