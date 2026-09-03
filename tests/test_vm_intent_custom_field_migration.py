"""Execute the VM-intent custom-field removal and restoration migration."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from tests.test_hardware_remainder_migration import (
    _Apps,
    _CF,
    _Obj,
    _ObjManager,
    _Schema,
    _install_stub,
)

MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "netbox_proxbox"
    / "migrations"
    / "0089_remove_vm_intent_custom_fields.py"
)

# Transcribed from the production registry independently of the migration.
PRODUCTION_FIELDS = {
    "proxmox_node": (
        "text",
        "hidden",
        ("virtualization.virtualmachine", "dcim.device"),
    ),
    "proxmox_storage": (
        "text",
        "hidden",
        ("virtualization.virtualmachine", "dcim.device"),
    ),
    "proxmox_iso": ("text", "yes", ("virtualization.virtualmachine",)),
    "proxmox_template_vmid": (
        "integer",
        "yes",
        ("virtualization.virtualmachine",),
    ),
    "cloud_init_user": ("text", "yes", ("virtualization.virtualmachine",)),
    "cloud_init_ssh_keys": (
        "longtext",
        "yes",
        ("virtualization.virtualmachine",),
    ),
    "cloud_init_user_data": (
        "longtext",
        "yes",
        ("virtualization.virtualmachine",),
    ),
    "cloud_init_network": (
        "longtext",
        "yes",
        ("virtualization.virtualmachine",),
    ),
    "proxbox_intent_state": (
        "text",
        "hidden",
        ("virtualization.virtualmachine",),
    ),
    "proxbox_last_apply_run_id": (
        "text",
        "hidden",
        ("virtualization.virtualmachine",),
    ),
}


@pytest.fixture
def migration():
    _install_stub()
    spec = importlib.util.spec_from_file_location(
        "migration_0088_intent", MIGRATION_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _seed():
    apps = _Apps()
    for name, (field_type, ui_editable, bindings) in PRODUCTION_FIELDS.items():
        field = _CF(name, type=field_type, ui_editable=ui_editable)
        for dotted_name in bindings:
            app_label, model = dotted_name.split(".")
            field.object_types.members.append(
                apps.ct_manager.get(app_label=app_label, model=model)
            )
        apps.store[name] = field

    vm = _Obj(
        1,
        {name: None for name in PRODUCTION_FIELDS}
        | {
            "proxmox_iso": "",
            "cloud_init_ssh_keys": [],
            "cloud_init_network": {},
            "cloud_init_user_data": "#cloud-config\nusers: []",
            "keep": "operator-owned",
        },
    )
    device = _Obj(2, {"proxmox_node": None, "proxmox_storage": ""})
    apps.obj_managers[("virtualization", "VirtualMachine")] = _ObjManager([vm])
    apps.obj_managers[("dcim", "Device")] = _ObjManager([device])
    return apps, vm, device


def test_forward_strips_only_null_and_blank_fields_and_preserves_all_values(
    migration,
):
    apps, vm, device = _seed()

    migration.remove_vm_intent_custom_fields(apps, _Schema())

    assert set(apps.store) == {
        "cloud_init_ssh_keys",
        "cloud_init_network",
        "cloud_init_user_data",
    }
    assert vm.custom_field_data == {
        "cloud_init_ssh_keys": [],
        "cloud_init_network": {},
        "cloud_init_user_data": "#cloud-config\nusers: []",
        "keep": "operator-owned",
    }
    assert device.custom_field_data == {}
    for name in apps.store:
        assert apps.store[name].object_types.removed == []


def test_forward_locks_affected_rows_before_authoritative_reads_and_writes(
    migration,
):
    apps, _vm, _device = _seed()

    migration.remove_vm_intent_custom_fields(apps, _Schema())

    vm_manager = apps.obj_managers[("virtualization", "VirtualMachine")]
    device_manager = apps.obj_managers[("dcim", "Device")]
    assert vm_manager.select_for_update_calls >= 2
    assert device_manager.select_for_update_calls >= 2
    assert vm_manager.calls[-4:] == [
        "select_for_update",
        "only",
        "iterator",
        "bulk_update",
    ]
    assert device_manager.calls[-4:] == [
        "select_for_update",
        "only",
        "iterator",
        "bulk_update",
    ]


def test_reverse_restores_removed_definitions_and_keeps_populated_fields_untouched(
    migration,
):
    apps, vm, _device = _seed()
    migration.remove_vm_intent_custom_fields(apps, _Schema())
    protected = {name: apps.store[name] for name in apps.store}

    migration.restore_vm_intent_custom_fields(apps, _Schema())

    assert set(apps.store) == set(PRODUCTION_FIELDS)
    for name, (field_type, ui_editable, bindings) in PRODUCTION_FIELDS.items():
        field = apps.store[name]
        assert (field.type, field.ui_editable) == (field_type, ui_editable)
        actual_bindings = {
            f"{content_type.app_label}.{content_type.model}"
            for content_type in field.object_types.members
        }
        assert actual_bindings == set(bindings)
    for name, field in protected.items():
        assert apps.store[name] is field
        assert field.object_types.added == []
    assert vm.custom_field_data["cloud_init_ssh_keys"] == []
    assert vm.custom_field_data["cloud_init_network"] == {}
    assert vm.custom_field_data["cloud_init_user_data"] == ("#cloud-config\nusers: []")
