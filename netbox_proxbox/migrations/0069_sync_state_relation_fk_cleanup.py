"""Promote sync-state relation FK staging columns to final names."""

from __future__ import annotations

from django.db import migrations


BATCH_SIZE = 1000


def _is_blank(value) -> bool:
    return value is None or value == ""


def _assert_relation_values_preserved(
    Target,
    *,
    legacy_field: str,
    fk_attname: str,
    raw_field: str,
    raw_value_field: str,
) -> None:
    missing = []
    for obj in Target.objects.all().iterator(chunk_size=BATCH_SIZE):
        legacy_value = getattr(obj, legacy_field)
        if _is_blank(legacy_value):
            continue
        if getattr(obj, fk_attname) is not None:
            continue
        if getattr(obj, raw_field) is not None:
            continue
        if not _is_blank(getattr(obj, raw_value_field)):
            continue
        missing.append(
            f"{Target._meta.label} pk={obj.pk!r} {legacy_field}={legacy_value!r}"
        )
        if len(missing) >= 20:
            break
    if missing:
        raise RuntimeError(
            "Refusing to drop legacy sync-state relation JSON before migration "
            "0068 has preserved every unresolved value: " + "; ".join(missing)
        )


def assert_relation_values_preserved(apps, schema_editor) -> None:
    DiskState = apps.get_model("netbox_proxbox", "ProxboxVirtualDiskSyncState")
    VMInterfaceState = apps.get_model(
        "netbox_proxbox",
        "ProxboxVMInterfaceSyncState",
    )

    _assert_relation_values_preserved(
        DiskState,
        legacy_field="proxbox_storage_id",
        fk_attname="proxbox_storage_fk_id",
        raw_field="proxbox_storage_raw_id",
        raw_value_field="proxbox_storage_raw_value",
    )
    _assert_relation_values_preserved(
        VMInterfaceState,
        legacy_field="proxbox_bridge",
        fk_attname="proxbox_bridge_fk_id",
        raw_field="proxbox_bridge_raw_id",
        raw_value_field="proxbox_bridge_raw_value",
    )


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0068_sync_state_relation_fk_data"),
    ]

    operations = [
        migrations.RunPython(
            assert_relation_values_preserved,
            migrations.RunPython.noop,
        ),
        migrations.RemoveField(
            model_name="proxboxvirtualdisksyncstate",
            name="proxbox_storage_id",
        ),
        migrations.RenameField(
            model_name="proxboxvirtualdisksyncstate",
            old_name="proxbox_storage_fk",
            new_name="proxbox_storage",
        ),
        migrations.RemoveField(
            model_name="proxboxvminterfacesyncstate",
            name="proxbox_bridge",
        ),
        migrations.RenameField(
            model_name="proxboxvminterfacesyncstate",
            old_name="proxbox_bridge_fk",
            new_name="proxbox_bridge",
        ),
    ]
