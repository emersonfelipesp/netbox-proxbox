"""Convert legacy sync-state storage and bridge JSON values into FKs."""

from __future__ import annotations

from collections.abc import Mapping
import json
import logging

from django.db import migrations


LOGGER = logging.getLogger(__name__)
BIGINT_MIN = -(2**63)
BIGINT_MAX = 2**63 - 1
BATCH_SIZE = 1000


def _is_blank(value) -> bool:
    return value is None or value == ""


def _to_preserved_text(value) -> str:
    if _is_blank(value):
        return ""
    try:
        return json.dumps(value, sort_keys=True, default=str)
    except TypeError:
        return str(value)


def _from_preserved_text(value: str):
    if _is_blank(value):
        return None
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return value


def _to_bigint(value) -> tuple[int | None, str | None]:
    if _is_blank(value) or isinstance(value, bool):
        return None, "non-integral"
    if isinstance(value, int):
        integer = value
    elif isinstance(value, float):
        if not value.is_integer():
            return None, "non-integral"
        integer = int(value)
    else:
        text = str(value).strip()
        if not text:
            return None, "non-integral"
        try:
            integer = int(text)
        except (OverflowError, TypeError, ValueError):
            return None, "non-integral"

    if not BIGINT_MIN <= integer <= BIGINT_MAX:
        return None, "out-of-range"
    return integer, None


def _extract_legacy_pk(value) -> tuple[int | None, str | None]:
    if isinstance(value, Mapping):
        for key in ("id", "pk", "value"):
            if key in value:
                return _extract_legacy_pk(value[key])
        return None, "non-integral"
    return _to_bigint(value)


def _save_relation_conversion(obj, updates: dict[str, object]) -> None:
    for field_name, value in updates.items():
        setattr(obj, field_name, value)
    obj.save(update_fields=tuple(updates))


def _log_unresolved_legacy_value(
    Target,
    obj,
    *,
    legacy_field: str,
    raw_value,
    reason: str,
) -> None:
    LOGGER.warning(
        "Skipped %s.%s legacy relation value for %s pk=%r raw=%r: %s.",
        Target._meta.label,
        legacy_field,
        Target.__name__,
        obj.pk,
        raw_value,
        reason,
    )


def _iter_relation_batches(Target, *, legacy_field: str):
    batch = []
    candidate_ids = set()
    for obj in Target.objects.all().iterator(chunk_size=BATCH_SIZE):
        raw_value = getattr(obj, legacy_field)
        if _is_blank(raw_value):
            continue
        raw_id, reason = _extract_legacy_pk(raw_value)
        if raw_id is None:
            _log_unresolved_legacy_value(
                Target,
                obj,
                legacy_field=legacy_field,
                raw_value=raw_value,
                reason=reason or "non-integral",
            )
        else:
            candidate_ids.add(raw_id)
        batch.append((obj, raw_value, raw_id))
        if len(batch) >= BATCH_SIZE:
            yield batch, candidate_ids
            batch = []
            candidate_ids = set()
    if batch:
        yield batch, candidate_ids


def _convert_legacy_relation_values(
    Target,
    *,
    legacy_field: str,
    fk_attname: str,
    raw_field: str,
    raw_value_field: str,
    RelationTarget,
) -> None:
    processed = 0
    resolved = 0
    raw_fallbacks = 0
    for batch, candidate_ids in _iter_relation_batches(
        Target, legacy_field=legacy_field
    ):
        target_ids = set(
            RelationTarget.objects.filter(pk__in=candidate_ids).values_list(
                "pk",
                flat=True,
            )
        )
        for obj, raw_value, raw_id in batch:
            processed += 1
            fk_id = raw_id if raw_id in target_ids else None
            if fk_id is not None:
                resolved += 1
                preserved_raw_id = None
                preserved_value = ""
            elif raw_id is not None:
                raw_fallbacks += 1
                preserved_raw_id = raw_id
                preserved_value = ""
            else:
                raw_fallbacks += 1
                preserved_raw_id = None
                preserved_value = _to_preserved_text(raw_value)
            _save_relation_conversion(
                obj,
                {
                    raw_field: preserved_raw_id,
                    raw_value_field: preserved_value,
                    fk_attname: fk_id,
                },
            )
    LOGGER.info(
        "Converted %s.%s legacy relation values: processed=%s resolved=%s "
        "raw_fallbacks=%s.",
        Target._meta.label,
        legacy_field,
        processed,
        resolved,
        raw_fallbacks,
    )


def _restore_legacy_relation_batch(
    batch,
    *,
    legacy_field: str,
    fk_attname: str,
    raw_field: str,
    raw_value_field: str,
    RelationTarget,
) -> None:
    raw_candidate_ids = {
        getattr(obj, raw_field)
        for obj in batch
        if getattr(obj, fk_attname) is None and getattr(obj, raw_field) is not None
    }
    existing_raw_ids = set()
    if raw_candidate_ids:
        existing_raw_ids = set(
            RelationTarget.objects.filter(pk__in=raw_candidate_ids).values_list(
                "pk",
                flat=True,
            )
        )
    for obj in batch:
        value = getattr(obj, fk_attname)
        if value is None:
            value = _from_preserved_text(getattr(obj, raw_value_field))
        if value is None:
            raw_id = getattr(obj, raw_field)
            if raw_id is not None and raw_id not in existing_raw_ids:
                value = raw_id
        if value is None:
            continue
        _save_relation_conversion(obj, {legacy_field: value})


def _restore_legacy_relation_values(
    Target,
    *,
    legacy_field: str,
    fk_attname: str,
    raw_field: str,
    raw_value_field: str,
    RelationTarget,
) -> None:
    batch = []
    for obj in Target.objects.all().iterator(chunk_size=BATCH_SIZE):
        batch.append(obj)
        if len(batch) >= BATCH_SIZE:
            _restore_legacy_relation_batch(
                batch,
                legacy_field=legacy_field,
                fk_attname=fk_attname,
                raw_field=raw_field,
                raw_value_field=raw_value_field,
                RelationTarget=RelationTarget,
            )
            batch = []
    if batch:
        _restore_legacy_relation_batch(
            batch,
            legacy_field=legacy_field,
            fk_attname=fk_attname,
            raw_field=raw_field,
            raw_value_field=raw_value_field,
            RelationTarget=RelationTarget,
        )


def convert_sync_state_relation_fks(apps, schema_editor) -> None:
    Storage = apps.get_model("netbox_proxbox", "ProxmoxStorage")
    Interface = apps.get_model("dcim", "Interface")
    DiskState = apps.get_model("netbox_proxbox", "ProxboxVirtualDiskSyncState")
    VMInterfaceState = apps.get_model(
        "netbox_proxbox",
        "ProxboxVMInterfaceSyncState",
    )

    _convert_legacy_relation_values(
        DiskState,
        legacy_field="proxbox_storage_id",
        fk_attname="proxbox_storage_fk_id",
        raw_field="proxbox_storage_raw_id",
        raw_value_field="proxbox_storage_raw_value",
        RelationTarget=Storage,
    )
    _convert_legacy_relation_values(
        VMInterfaceState,
        legacy_field="proxbox_bridge",
        fk_attname="proxbox_bridge_fk_id",
        raw_field="proxbox_bridge_raw_id",
        raw_value_field="proxbox_bridge_raw_value",
        RelationTarget=Interface,
    )


def restore_legacy_relation_values(apps, schema_editor) -> None:
    Storage = apps.get_model("netbox_proxbox", "ProxmoxStorage")
    Interface = apps.get_model("dcim", "Interface")
    DiskState = apps.get_model("netbox_proxbox", "ProxboxVirtualDiskSyncState")
    VMInterfaceState = apps.get_model(
        "netbox_proxbox",
        "ProxboxVMInterfaceSyncState",
    )

    _restore_legacy_relation_values(
        DiskState,
        legacy_field="proxbox_storage_id",
        fk_attname="proxbox_storage_fk_id",
        raw_field="proxbox_storage_raw_id",
        raw_value_field="proxbox_storage_raw_value",
        RelationTarget=Storage,
    )
    _restore_legacy_relation_values(
        VMInterfaceState,
        legacy_field="proxbox_bridge",
        fk_attname="proxbox_bridge_fk_id",
        raw_field="proxbox_bridge_raw_id",
        raw_value_field="proxbox_bridge_raw_value",
        RelationTarget=Interface,
    )


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("netbox_proxbox", "0067_sync_state_relation_fks"),
    ]

    operations = [
        migrations.RunPython(
            convert_sync_state_relation_fks,
            restore_legacy_relation_values,
        ),
    ]
