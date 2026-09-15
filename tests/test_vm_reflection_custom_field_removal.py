"""Contracts for VM reflection custom-field removal migration 0084."""

from __future__ import annotations

import ast
from pathlib import Path


MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "netbox_proxbox"
    / "migrations"
    / "0085_remove_vm_reflection_custom_fields.py"
)

TARGET_NAMES = {
    "proxmox_vm_id",
    "proxmox_vm_type",
    "proxmox_start_at_boot",
    "proxmox_unprivileged_container",
    "proxmox_qemu_agent",
    "proxmox_search_domain",
    "proxmox_status",
    "proxmox_uptime",
    "proxmox_migration_duration",
    "proxmox_migration_type",
    "proxmox_endpoint_id",
    "proxmox_last_synced_role_id",
}

OUT_OF_SCOPE_NAMES = {
    "proxmox_last_updated",
    "proxbox_last_run_id",
    "proxmox_cluster",
    "proxmox_node",
    "proxmox_link",
    "proxmox_tags",
    "proxmox_os",
    "proxmox_storage",
    "proxmox_disk",
    "proxmox_interfaces",
    "proxmox_vmid",
    "proxmox_notes",
    "proxmox_tcp_states",
    "proxmox_cpu_type",
    "proxmox_storage_ids",
    "proxmox_storage_names",
    "proxmox_device_names",
    "proxmox_iso",
    "proxmox_template_vmid",
    "cloud_init_user",
    "cloud_init_ssh_keys",
    "cloud_init_user_data",
    "cloud_init_network",
    "proxbox_intent_state",
    "proxbox_last_apply_run_id",
    "source_packer_template",
    "netbox_proxy_url",
}


def _assignment_value(name: str):
    tree = ast.parse(MIGRATION_PATH.read_text())
    for statement in tree.body:
        if not isinstance(statement, ast.Assign):
            continue
        if any(
            isinstance(target, ast.Name) and target.id == name
            for target in statement.targets
        ):
            return ast.literal_eval(statement.value)
    raise AssertionError(f"Missing migration constant {name}")


def test_migration_names_exactly_the_twelve_vm_reflection_fields() -> None:
    names = set(_assignment_value("VM_REFLECTION_CUSTOM_FIELD_NAMES"))

    assert names == TARGET_NAMES
    assert names.isdisjoint(OUT_OF_SCOPE_NAMES)


def test_reverse_definition_table_is_complete_and_explicit() -> None:
    definitions = _assignment_value("VM_REFLECTION_CUSTOM_FIELD_DEFINITIONS")

    assert {definition["name"] for definition in definitions} == TARGET_NAMES
    assert len(definitions) == len(TARGET_NAMES)
    assert all("type" in definition for definition in definitions)
    assert all("label" in definition for definition in definitions)
    assert all("description" in definition for definition in definitions)
    assert all("ui_visible" in definition for definition in definitions)
    assert all("ui_editable" in definition for definition in definitions)


def test_forward_is_idempotent_and_strips_only_named_vm_json_keys() -> None:
    source = MIGRATION_PATH.read_text()

    assert (
        ".filter(\n        name__in=VM_REFLECTION_CUSTOM_FIELD_NAMES\n    ).delete()"
        in source
    )
    assert "for name in VM_REFLECTION_CUSTOM_FIELD_NAMES:" in source
    assert "cleaned.pop(name, None)" in source
    assert "bulk_update(" in source
    assert 'name="custom_fields_enabled"' in source


def test_reverse_restores_definitions_and_virtual_machine_bindings() -> None:
    source = MIGRATION_PATH.read_text()

    assert "manager.update_or_create(" in source
    assert "custom_field.object_types.add(vm_content_type)" in source
    assert 'app_label="virtualization"' in source
    assert 'model="virtualmachine"' in source
