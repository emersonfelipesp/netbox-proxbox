"""Remove VM-only reflection custom fields after typed-state cutover."""

from __future__ import annotations

from django.db import migrations


VM_REFLECTION_CUSTOM_FIELD_NAMES = (
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
)

VM_REFLECTION_CUSTOM_FIELD_DEFINITIONS = (
    {
        "name": "proxmox_vm_id",
        "type": "integer",
        "label": "VM ID",
        "description": "Proxmox Virtual Machine or Container ID",
        "ui_visible": "always",
        "ui_editable": "hidden",
        "weight": 100,
        "filter_logic": "loose",
        "search_weight": 1000,
        "group_name": "Proxmox",
    },
    {
        "name": "proxmox_vm_type",
        "type": "text",
        "label": "VM Type",
        "description": "Proxmox VM type (qemu or lxc)",
        "ui_visible": "always",
        "ui_editable": "hidden",
        "weight": 100,
        "filter_logic": "loose",
        "search_weight": 1000,
        "group_name": "Proxmox",
    },
    {
        "name": "proxmox_start_at_boot",
        "type": "boolean",
        "label": "Start at Boot",
        "description": "Proxmox Start at Boot Option",
        "ui_visible": "always",
        "ui_editable": "hidden",
        "weight": 100,
        "filter_logic": "loose",
        "search_weight": 1000,
        "group_name": "Proxmox",
    },
    {
        "name": "proxmox_unprivileged_container",
        "type": "boolean",
        "label": "Unprivileged Container",
        "description": "Proxmox Unprivileged Container",
        "ui_visible": "if-set",
        "ui_editable": "hidden",
        "weight": 100,
        "filter_logic": "loose",
        "search_weight": 1000,
        "group_name": "Proxmox",
    },
    {
        "name": "proxmox_qemu_agent",
        "type": "boolean",
        "label": "QEMU Guest Agent",
        "description": "Proxmox QEMU Guest Agent",
        "ui_visible": "if-set",
        "ui_editable": "hidden",
        "weight": 100,
        "filter_logic": "loose",
        "search_weight": 1000,
        "group_name": "Proxmox",
    },
    {
        "name": "proxmox_search_domain",
        "type": "text",
        "label": "Search Domain",
        "description": "Proxmox Search Domain",
        "ui_visible": "if-set",
        "ui_editable": "hidden",
        "weight": 100,
        "filter_logic": "loose",
        "search_weight": 1000,
        "group_name": "Proxmox",
    },
    {
        "name": "proxmox_status",
        "type": "text",
        "label": "Proxmox Status",
        "description": "Current status in Proxmox",
        "ui_visible": "always",
        "ui_editable": "hidden",
        "weight": 100,
        "filter_logic": "loose",
        "search_weight": 1000,
        "group_name": "Proxmox",
    },
    {
        "name": "proxmox_uptime",
        "type": "integer",
        "label": "Uptime (seconds)",
        "description": "VM uptime in seconds",
        "ui_visible": "if-set",
        "ui_editable": "hidden",
        "weight": 100,
        "filter_logic": "loose",
        "search_weight": 1000,
        "group_name": "Proxmox",
    },
    {
        "name": "proxmox_migration_duration",
        "type": "integer",
        "label": "Migration Duration",
        "description": "Migration duration in seconds",
        "ui_visible": "if-set",
        "ui_editable": "hidden",
        "weight": 100,
        "filter_logic": "loose",
        "search_weight": 1000,
        "group_name": "Proxmox",
    },
    {
        "name": "proxmox_migration_type",
        "type": "text",
        "label": "Migration Type",
        "description": "Migration type (live / offline)",
        "ui_visible": "if-set",
        "ui_editable": "hidden",
        "weight": 100,
        "filter_logic": "loose",
        "search_weight": 1000,
        "group_name": "Proxmox",
    },
    {
        "name": "proxmox_endpoint_id",
        "type": "integer",
        "label": "Proxmox Endpoint ID",
        "description": "proxbox-api ProxmoxEndpoint database ID for console access",
        "ui_visible": "if-set",
        "ui_editable": "hidden",
        "weight": 100,
        "filter_logic": "loose",
        "search_weight": 1000,
        "group_name": "Proxmox",
    },
    {
        "name": "proxmox_last_synced_role_id",
        "type": "integer",
        "label": "Proxmox last-synced role id",
        "description": (
            "Snapshot of the role id last written by Proxbox sync. Used to detect "
            "operator edits to the VM role between sync runs. Managed automatically "
            "by Proxbox; do not edit."
        ),
        "ui_visible": "hidden",
        "ui_editable": "hidden",
        "filter_logic": "disabled",
        "required": False,
        "search_weight": 0,
    },
)

_BATCH_SIZE = 500


def remove_vm_reflection_custom_fields(apps, schema_editor) -> None:
    """Delete the twelve definitions and their stale VM JSON values."""
    CustomField = apps.get_model("extras", "CustomField")
    VirtualMachine = apps.get_model("virtualization", "VirtualMachine")
    db_alias = schema_editor.connection.alias

    CustomField.objects.using(db_alias).filter(
        name__in=VM_REFLECTION_CUSTOM_FIELD_NAMES
    ).delete()

    pending = []
    rows = (
        VirtualMachine.objects.using(db_alias)
        .only("pk", "custom_field_data")
        .iterator(chunk_size=_BATCH_SIZE)
    )
    for vm in rows:
        data = vm.custom_field_data
        if not isinstance(data, dict):
            continue
        cleaned = dict(data)
        for name in VM_REFLECTION_CUSTOM_FIELD_NAMES:
            cleaned.pop(name, None)
        if cleaned == data:
            continue
        vm.custom_field_data = cleaned
        pending.append(vm)
        if len(pending) >= _BATCH_SIZE:
            VirtualMachine.objects.using(db_alias).bulk_update(
                pending,
                ("custom_field_data",),
                batch_size=_BATCH_SIZE,
            )
            pending.clear()
    if pending:
        VirtualMachine.objects.using(db_alias).bulk_update(
            pending,
            ("custom_field_data",),
            batch_size=_BATCH_SIZE,
        )


def restore_vm_reflection_custom_fields(apps, schema_editor) -> None:
    """Restore the original definitions and VirtualMachine bindings."""
    ContentType = apps.get_model("contenttypes", "ContentType")
    CustomField = apps.get_model("extras", "CustomField")
    db_alias = schema_editor.connection.alias
    try:
        vm_content_type = ContentType.objects.using(db_alias).get(
            app_label="virtualization",
            model="virtualmachine",
        )
    except ContentType.DoesNotExist:
        return

    manager = CustomField.objects.using(db_alias)
    for definition in VM_REFLECTION_CUSTOM_FIELD_DEFINITIONS:
        defaults = {
            key: value for key, value in definition.items() if key != "name"
        }
        custom_field, _created = manager.update_or_create(
            name=definition["name"],
            defaults=defaults,
        )
        custom_field.object_types.add(vm_content_type)


class Migration(migrations.Migration):
    dependencies = [
        # Depends on the console-URL migration rather than 0083 directly. Both
        # were written against 0083 on separate branches and merged in the same
        # window, which left two leaf nodes in the migration graph and made
        # every `migrate` refuse to run for the whole plugin. Linearising behind
        # it restores a single leaf; a merge migration would also work but adds
        # an empty node for nothing. The two touch unrelated state, so the order
        # carries no further meaning.
        ("netbox_proxbox", "0084_proxboxpluginsettings_console_url"),
    ]

    operations = [
        migrations.RunPython(
            remove_vm_reflection_custom_fields,
            reverse_code=restore_vm_reflection_custom_fields,
        ),
        migrations.RemoveField(
            model_name="proxboxpluginsettings",
            name="custom_fields_enabled",
        ),
    ]
