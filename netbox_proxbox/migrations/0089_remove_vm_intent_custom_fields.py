"""Retire empty VM-intent custom fields after adding ``ProxmoxVMIntent``.

The ownership and emptiness boundary matches migration 0087. A field is a
candidate only when its type and ``ui_editable`` value match the live registry.
It is then left entirely untouched if any bound object stores anything other
than ``None`` or the empty string under either accepted JSON spelling. The
check runs before locking, again after the definitions and affected object rows
are locked, and once more immediately before each blank key is stripped.

Forward deletion is therefore intentionally conservative and irreversible only
for blank metadata. Reverse restores the live definition and canonical bindings
but cannot and need not reconstruct values: forward never removes a value.
"""

from __future__ import annotations

from django.db import migrations

VM_INTENT_CUSTOM_FIELD_DEFINITIONS = (
    {
        "name": "proxmox_node",
        "object_types": ("virtualization.virtualmachine", "dcim.device"),
        "type": "text",
        "label": "Proxmox Node",
        "description": "Proxmox node hosting this device/VM",
        "ui_visible": "always",
        "ui_editable": "hidden",
        "weight": 100,
        "filter_logic": "loose",
        "required": False,
        "search_weight": 1000,
        "group_name": "Proxmox",
    },
    {
        "name": "proxmox_storage",
        "object_types": ("virtualization.virtualmachine", "dcim.device"),
        "type": "text",
        "label": "Storage",
        "description": "Storage disk size",
        "ui_visible": "if-set",
        "ui_editable": "hidden",
        "weight": 100,
        "filter_logic": "loose",
        "required": False,
        "search_weight": 1000,
        "group_name": "Proxmox",
    },
    {
        "name": "proxmox_iso",
        "object_types": ("virtualization.virtualmachine",),
        "type": "text",
        "label": "Proxmox ISO volume id",
        "description": (
            "Optional Proxmox volume id of the install ISO. Empty means no ISO "
            "is attached on CREATE."
        ),
        "ui_visible": "always",
        "ui_editable": "yes",
        "weight": 100,
        "filter_logic": "loose",
        "required": False,
        "search_weight": 0,
        "group_name": "",
    },
    {
        "name": "proxmox_template_vmid",
        "object_types": ("virtualization.virtualmachine",),
        "type": "integer",
        "label": "Proxmox template VMID",
        "description": (
            "Source VMID to clone from when creating this VM. Mutually exclusive "
            "with ISO-driven CREATE; both empty means an empty VM."
        ),
        "ui_visible": "always",
        "ui_editable": "yes",
        "weight": 100,
        "filter_logic": "loose",
        "required": False,
        "search_weight": 0,
        "group_name": "",
    },
    {
        "name": "cloud_init_user",
        "object_types": ("virtualization.virtualmachine",),
        "type": "text",
        "label": "Cloud-Init user",
        "description": (
            "Default cloud-init username (Proxmox ``ciuser``). Optional; empty "
            "means inherit the Proxmox default. See Sub-PR K."
        ),
        "ui_visible": "always",
        "ui_editable": "yes",
        "weight": 100,
        "filter_logic": "loose",
        "required": False,
        "search_weight": 0,
        "group_name": "",
    },
    {
        "name": "cloud_init_ssh_keys",
        "object_types": ("virtualization.virtualmachine",),
        "type": "longtext",
        "label": "Cloud-Init SSH keys",
        "description": (
            "Newline-separated authorized SSH public keys (Proxmox ``sshkeys``). "
            "See Sub-PR K."
        ),
        "ui_visible": "always",
        "ui_editable": "yes",
        "weight": 100,
        "filter_logic": "loose",
        "required": False,
        "search_weight": 0,
        "group_name": "",
    },
    {
        "name": "cloud_init_user_data",
        "object_types": ("virtualization.virtualmachine",),
        "type": "longtext",
        "label": "Cloud-Init user-data (YAML)",
        "description": (
            "Optional raw cloud-init user-data YAML rendered via ``cicustom``. "
            "Plan-time warning if it contains a literal ``password:`` key. See "
            "Sub-PR K."
        ),
        "ui_visible": "always",
        "ui_editable": "yes",
        "weight": 100,
        "filter_logic": "loose",
        "required": False,
        "search_weight": 0,
        "group_name": "",
    },
    {
        "name": "cloud_init_network",
        "object_types": ("virtualization.virtualmachine",),
        "type": "longtext",
        "label": "Cloud-Init network config",
        "description": (
            "Optional cloud-init network config block (``ipconfig0`` style). See "
            "Sub-PR K."
        ),
        "ui_visible": "always",
        "ui_editable": "yes",
        "weight": 100,
        "filter_logic": "loose",
        "required": False,
        "search_weight": 0,
        "group_name": "",
    },
    {
        "name": "proxbox_intent_state",
        "object_types": ("virtualization.virtualmachine",),
        "type": "text",
        "label": "Proxbox intent state",
        "description": (
            "Last terminal intent verdict for this VM. One of ``applied``, "
            "``pending``, ``failed``. Written by proxbox-api after an apply run; "
            "do not edit by hand."
        ),
        "ui_visible": "hidden",
        "ui_editable": "hidden",
        "weight": 100,
        "filter_logic": "disabled",
        "required": False,
        "search_weight": 0,
        "group_name": "",
    },
    {
        "name": "proxbox_last_apply_run_id",
        "object_types": ("virtualization.virtualmachine",),
        "type": "text",
        "label": "Proxbox last apply run id",
        "description": (
            "UUID of the most recent ProxmoxApplyJob touching this VM. Used to "
            "correlate the VM row with the apply log; managed by Proxbox."
        ),
        "ui_visible": "hidden",
        "ui_editable": "hidden",
        "weight": 100,
        "filter_logic": "disabled",
        "required": False,
        "search_weight": 0,
        "group_name": "",
    },
)

VM_INTENT_CUSTOM_FIELD_NAMES = tuple(
    definition["name"] for definition in VM_INTENT_CUSTOM_FIELD_DEFINITIONS
)
AFFECTED_OBJECT_TYPES = (
    ("virtualization", "VirtualMachine"),
    ("dcim", "Device"),
)
_OWNERSHIP_FIELDS = ("type", "ui_editable")
_BATCH_SIZE = 500


def _content_type(ContentType, db_alias: str, dotted_name: str):
    app_label, model = dotted_name.split(".", 1)
    try:
        return ContentType.objects.using(db_alias).get(app_label=app_label, model=model)
    except ContentType.DoesNotExist:
        return None


def _is_ours(custom_field, definition) -> bool:
    for attribute in _OWNERSHIP_FIELDS:
        expected = definition.get(attribute)
        if expected is not None and getattr(custom_field, attribute, None) != expected:
            return False
    return True


def _holds_data(data: dict, key: str) -> bool:
    """Treat only a missing key, ``None``, or the empty string as blank."""
    return key in data and data[key] not in (None, "")


def _names_holding_data(
    model, db_alias: str, names: set, *, lock_rows: bool = False
) -> set:
    if not names:
        return set()
    found: set = set()
    queryset = model.objects.using(db_alias)
    if lock_rows:
        queryset = queryset.select_for_update()
    rows = queryset.only("pk", "custom_field_data").iterator(chunk_size=_BATCH_SIZE)
    for obj in rows:
        data = obj.custom_field_data
        if not isinstance(data, dict):
            continue
        for name in names - found:
            if any(_holds_data(data, key) for key in (name, f"cf_{name}")):
                found.add(name)
        if found == names:
            break
    return found


def _strip_values(model, db_alias: str, names: set) -> None:
    if not names:
        return
    pending = []
    rows = (
        model.objects.using(db_alias)
        .select_for_update()
        .only("pk", "custom_field_data")
        .iterator(chunk_size=_BATCH_SIZE)
    )
    for obj in rows:
        data = obj.custom_field_data
        if not isinstance(data, dict):
            continue
        cleaned = dict(data)
        for name in names:
            for key in (name, f"cf_{name}"):
                # Third emptiness check: refuse a value written after the scans.
                if key in cleaned and not _holds_data(cleaned, key):
                    del cleaned[key]
        if cleaned == data:
            continue
        obj.custom_field_data = cleaned
        pending.append(obj)
        if len(pending) >= _BATCH_SIZE:
            model.objects.using(db_alias).bulk_update(
                pending, ("custom_field_data",), batch_size=_BATCH_SIZE
            )
            pending.clear()
    if pending:
        model.objects.using(db_alias).bulk_update(
            pending, ("custom_field_data",), batch_size=_BATCH_SIZE
        )


def _canonical_type_pks(ContentType, db_alias: str, definition) -> set:
    pks = set()
    for dotted_name in definition["object_types"]:
        content_type = _content_type(ContentType, db_alias, dotted_name)
        if content_type is not None:
            pks.add(content_type.pk)
    return pks


def _release_one_field(custom_field, definition, ContentType, db_alias: str) -> None:
    canonical = _canonical_type_pks(ContentType, db_alias, definition)
    bound = set(custom_field.object_types.values_list("pk", flat=True))
    if canonical:
        custom_field.object_types.remove(*canonical)
    if not (bound - canonical):
        custom_field.delete()


def _released_names_by_type() -> dict:
    released: dict = {}
    for definition in VM_INTENT_CUSTOM_FIELD_DEFINITIONS:
        for dotted_name in definition["object_types"]:
            released.setdefault(dotted_name, set()).add(definition["name"])
    return released


def _populated_names(
    apps, db_alias: str, released_by_type: dict, *, lock_rows: bool = False
) -> set:
    populated: set = set()
    for app_label, model_name in AFFECTED_OBJECT_TYPES:
        names = released_by_type.get(f"{app_label}.{model_name}".lower())
        if names:
            model = apps.get_model(app_label, model_name)
            populated |= _names_holding_data(
                model, db_alias, set(names), lock_rows=lock_rows
            )
    return populated


def remove_vm_intent_custom_fields(apps, schema_editor) -> None:
    """Release only owned intent definitions that are empty everywhere."""
    ContentType = apps.get_model("contenttypes", "ContentType")
    CustomField = apps.get_model("extras", "CustomField")
    db_alias = schema_editor.connection.alias
    definitions = {
        definition["name"]: definition
        for definition in VM_INTENT_CUSTOM_FIELD_DEFINITIONS
    }
    released_by_type = _released_names_by_type()

    # First emptiness check permits a quick refusal before taking row locks.
    skipped = _populated_names(apps, db_alias, released_by_type)
    locked = (
        CustomField.objects.using(db_alias)
        .filter(name__in=VM_INTENT_CUSTOM_FIELD_NAMES)
        .select_for_update()
    )
    # Second emptiness check is authoritative under the definition locks.
    skipped |= _populated_names(apps, db_alias, released_by_type, lock_rows=True)

    for custom_field in locked:
        definition = definitions.get(custom_field.name)
        if definition is None or custom_field.name in skipped:
            continue
        if _is_ours(custom_field, definition):
            _release_one_field(custom_field, definition, ContentType, db_alias)
        else:
            skipped.add(custom_field.name)

    for app_label, model_name in AFFECTED_OBJECT_TYPES:
        names = released_by_type.get(f"{app_label}.{model_name}".lower(), set())
        _strip_values(apps.get_model(app_label, model_name), db_alias, names - skipped)


def _may_rebind(apps, db_alias: str, custom_field, definition) -> bool:
    if not _is_ours(custom_field, definition):
        return False
    for dotted_name in definition["object_types"]:
        app_label, model_name = dotted_name.split(".", 1)
        for candidate_app, candidate_model in AFFECTED_OBJECT_TYPES:
            if (candidate_app, candidate_model.lower()) != (app_label, model_name):
                continue
            model = apps.get_model(candidate_app, candidate_model)
            if _names_holding_data(model, db_alias, {definition["name"]}):
                return False
    return True


def restore_vm_intent_custom_fields(apps, schema_editor) -> None:
    """Restore live definitions, without rebinding an existing populated row."""
    ContentType = apps.get_model("contenttypes", "ContentType")
    CustomField = apps.get_model("extras", "CustomField")
    db_alias = schema_editor.connection.alias
    manager = CustomField.objects.using(db_alias)

    for definition in VM_INTENT_CUSTOM_FIELD_DEFINITIONS:
        object_types = [
            content_type
            for dotted_name in definition["object_types"]
            if (content_type := _content_type(ContentType, db_alias, dotted_name))
            is not None
        ]
        if not object_types:
            continue
        defaults = {
            key: value
            for key, value in definition.items()
            if key not in {"name", "object_types"}
        }
        custom_field, created = manager.get_or_create(
            name=definition["name"], defaults=defaults
        )
        if not created and not _may_rebind(apps, db_alias, custom_field, definition):
            continue
        for content_type in object_types:
            custom_field.object_types.add(content_type)


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0088_proxmox_vm_intent"),
    ]

    operations = [
        migrations.RunPython(
            remove_vm_intent_custom_fields,
            reverse_code=restore_vm_intent_custom_fields,
        ),
    ]
