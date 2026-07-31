"""Persist VM role-ownership evidence in the typed sync-state sidecar.

The deprecated ``proxmox_last_synced_role_id`` VirtualMachine custom field was
the original ownership lock: when the current role diverges from that snapshot,
sync must treat the role as an operator edit. Typed sync-state sidecars replaced
legacy reflection custom fields, but the VM sidecar omitted this one value. With
legacy custom fields disabled, proxbox-api therefore saw no ownership evidence
and could repeatedly write the configured default role.

The schema change is additive and idempotent. Existing valid legacy values are
copied without overwriting a typed value, and legacy data is deliberately left
in place for mixed-version rollback compatibility.
"""

from __future__ import annotations

from collections.abc import Mapping

from django.db import migrations, models

from netbox_proxbox.migrations._idempotent_ops import add_field_idempotent


LEGACY_CUSTOM_FIELD = "proxmox_last_synced_role_id"
MAX_SIGNED_BIGINT = 9_223_372_036_854_775_807
BACKFILL_BATCH_SIZE = 500


def _positive_role_id(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str) and value.strip().isdigit():
        parsed = int(value.strip())
    else:
        return None
    return parsed if 0 < parsed <= MAX_SIGNED_BIGINT else None


def _backfill_batch(
    SyncState, *, database_alias: str, candidates: dict[int, int]
) -> None:
    if not candidates:
        return

    manager = SyncState.objects.using(database_alias)
    existing_by_vm_id = {
        row.virtual_machine_id: row
        for row in manager.filter(virtual_machine_id__in=candidates)
    }
    manager.bulk_create(
        [
            SyncState(
                virtual_machine_id=vm_id,
                proxmox_last_synced_role_id=role_id,
            )
            for vm_id, role_id in candidates.items()
            if vm_id not in existing_by_vm_id
        ],
        batch_size=BACKFILL_BATCH_SIZE,
        ignore_conflicts=True,
    )

    updates = []
    for vm_id, row in existing_by_vm_id.items():
        if row.proxmox_last_synced_role_id is not None:
            continue
        row.proxmox_last_synced_role_id = candidates[vm_id]
        updates.append(row)
    if updates:
        manager.bulk_update(
            updates,
            ["proxmox_last_synced_role_id"],
            batch_size=BACKFILL_BATCH_SIZE,
        )


def backfill_last_synced_role(apps, schema_editor) -> None:
    VirtualMachine = apps.get_model("virtualization", "VirtualMachine")
    SyncState = apps.get_model(
        "netbox_proxbox",
        "ProxboxVirtualMachineSyncState",
    )

    database_alias = (
        schema_editor.connection.alias if schema_editor is not None else "default"
    )
    candidates: dict[int, int] = {}
    virtual_machines = (
        VirtualMachine.objects.using(database_alias)
        .only("pk", "custom_field_data")
        .iterator(chunk_size=BACKFILL_BATCH_SIZE)
    )
    for virtual_machine in virtual_machines:
        custom_fields = getattr(virtual_machine, "custom_field_data", None)
        if not isinstance(custom_fields, Mapping):
            continue
        role_id = _positive_role_id(
            custom_fields.get(
                LEGACY_CUSTOM_FIELD,
                custom_fields.get(f"cf_{LEGACY_CUSTOM_FIELD}"),
            )
        )
        if role_id is None:
            continue
        candidates[virtual_machine.pk] = role_id
        if len(candidates) >= BACKFILL_BATCH_SIZE:
            _backfill_batch(
                SyncState,
                database_alias=database_alias,
                candidates=candidates,
            )
            candidates = {}
    _backfill_batch(
        SyncState,
        database_alias=database_alias,
        candidates=candidates,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0077_ceph_runtime_timing_settings"),
    ]

    operations = [
        add_field_idempotent(
            model_name="proxboxvirtualmachinesyncstate",
            field_name="proxmox_last_synced_role_id",
            field=models.PositiveBigIntegerField(
                blank=True,
                null=True,
                help_text=(
                    "DeviceRole ID last written by Proxbox. Used to preserve "
                    "operator role edits while allowing sync-managed roles to "
                    "roll forward."
                ),
            ),
        ),
        migrations.RunPython(
            backfill_last_synced_role,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
