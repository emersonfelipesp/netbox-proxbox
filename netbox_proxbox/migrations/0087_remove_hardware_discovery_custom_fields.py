"""Retire the six hardware-discovery reflection custom fields 0086 skipped.

`0086` refused these because its ownership check compared the field's label
against the definition this plugin's own `_v0_0_15_release_data` migration
wrote -- `Chassis manufacturer`. proxbox-api's custom-field inventory had since
reconciled them, and it does not merely recase: it writes `Chassis Product`
where the migration wrote `Chassis product name`, and it describes the chassis
manufacturer as coming from `dmidecode -t 3` where the migration said `-t 1`.
0086 saw a mismatch and failed closed, leaving all six in place.

Failing closed was correct behaviour: the check exists so a field an operator
repurposed is never deleted, and it cannot tell "somebody changed this" from
"somebody else's field". What was wrong is treating **label** as evidence of
ownership. Two writers inside this project disagree about both the label and
the description of these exact fields, so neither is a signal -- an operator's
cosmetic edit is indistinguishable from our own.

What both writers do agree on, and what an operator repurposing a field for
their own data would have to change, is `ui_editable="hidden"`. A field nobody
can edit is not a field somebody is keeping data in. So the predicate here is
the **data type** plus that hidden flag: type says the field is the shape we
created, and the flag says it is still ours to write. The bindings must still
be ours as well, and a row carrying any binding this plugin did not create
keeps its row, that binding, and its stored values.

Neither signal is provenance, and NetBox records none: it has no owner column
on a custom field, and every attribute an operator can reach is mutable.
`ui_editable="hidden"` in particular stops the edit form, not the REST API, so
a hidden field can still be where an integration keeps data. So the shape
checks decide only which fields are *candidates*, and the destructive step is
gated on the question that actually matters: **a field holding a value on any
row is left alone in full** -- definition, bindings and values -- whoever wrote
it. Deletion is reached only for a field of our type, not operator-editable,
and empty everywhere.

**Stripped values are not restorable.** Forward removes the six keys from
`custom_field_data` without journaling them, exactly as 0085 and 0086 do, so
the reverse restores definitions and bindings but not values. With the
emptiness gate above there is nothing to journal: a field that holds anything
is never stripped. On this estate that was also confirmed directly -- all 44
production devices and all 1,459 production interfaces carry `None` for every
one of the six. The reverse leaves a row forward skipped completely untouched,
so a rollback cannot hand an operator's field a Proxbox binding it never had.

`0086` is left exactly as applied. Its skip is safe and merely incomplete, and
rewriting an already-applied migration body would change history that staging
and production have run.
"""

from __future__ import annotations

from django.db import migrations

HARDWARE_CUSTOM_FIELD_NAMES = (
    "hardware_chassis_manufacturer",
    "hardware_chassis_product",
    "hardware_chassis_serial",
    "nic_duplex",
    "nic_link",
    "nic_speed_gbps",
)

# Every value below was read from the live registry, so a rollback recreates
# what production actually carried rather than the older spelling this
# plugin's own migration used. `ui_editable` doubles as the ownership signal;
# see this module's docstring.
HARDWARE_CUSTOM_FIELD_DEFINITIONS = (
    {
        "name": "hardware_chassis_manufacturer",
        "object_types": ("dcim.device",),
        "type": "text",
        "label": "Chassis Manufacturer",
        "description": "Chassis manufacturer reported by dmidecode -t 3",
        "ui_visible": "if-set",
        "ui_editable": "hidden",
        "weight": 300,
        "filter_logic": "loose",
        "required": False,
        "search_weight": 1000,
        "group_name": "Proxmox",
    },
    {
        "name": "hardware_chassis_product",
        "object_types": ("dcim.device",),
        "type": "text",
        "label": "Chassis Product",
        "description": "System product name reported by dmidecode -t 1",
        "ui_visible": "if-set",
        "ui_editable": "hidden",
        "weight": 300,
        "filter_logic": "loose",
        "required": False,
        "search_weight": 1000,
        "group_name": "Proxmox",
    },
    {
        "name": "hardware_chassis_serial",
        "object_types": ("dcim.device",),
        "type": "text",
        "label": "Chassis Serial",
        "description": "Chassis serial reported by dmidecode -t 3",
        "ui_visible": "if-set",
        "ui_editable": "hidden",
        "weight": 300,
        "filter_logic": "loose",
        "required": False,
        "search_weight": 1000,
        "group_name": "Proxmox",
    },
    {
        "name": "nic_duplex",
        "object_types": ("dcim.interface",),
        "type": "text",
        "label": "NIC Duplex",
        "description": "Duplex mode reported by ethtool",
        "ui_visible": "if-set",
        "ui_editable": "hidden",
        "weight": 300,
        "filter_logic": "loose",
        "required": False,
        "search_weight": 1000,
        "group_name": "Proxmox",
    },
    {
        "name": "nic_link",
        "object_types": ("dcim.interface",),
        "type": "boolean",
        "label": "NIC Link Up",
        "description": "Link-detected status reported by ethtool",
        "ui_visible": "if-set",
        "ui_editable": "hidden",
        "weight": 300,
        "filter_logic": "loose",
        "required": False,
        "search_weight": 1000,
        "group_name": "Proxmox",
    },
    {
        "name": "nic_speed_gbps",
        "object_types": ("dcim.interface",),
        "type": "integer",
        "label": "NIC Speed (Gbps)",
        "description": "Negotiated link speed reported by ethtool, in Gbps",
        "ui_visible": "if-set",
        "ui_editable": "hidden",
        "weight": 300,
        "filter_logic": "loose",
        "required": False,
        "search_weight": 1000,
        "group_name": "Proxmox",
    },
)

AFFECTED_OBJECT_TYPES = (
    ("dcim", "Device"),
    ("dcim", "Interface"),
)

_BATCH_SIZE = 500


def _content_type(ContentType, db_alias: str, dotted_name: str):
    app_label, model = dotted_name.split(".", 1)
    try:
        return ContentType.objects.using(db_alias).get(app_label=app_label, model=model)
    except ContentType.DoesNotExist:
        return None


# The two attributes both writers of these fields agree on. Label and
# description are deliberately absent: this plugin's own migration and
# proxbox-api's inventory disagree about both, so neither can distinguish our
# field from one an operator edited.
_OWNERSHIP_FIELDS = ("type", "ui_editable")


def _is_ours(custom_field, definition) -> bool:
    """True only for a field of our shape that is still ours to write."""
    for attribute in _OWNERSHIP_FIELDS:
        expected = definition.get(attribute)
        if expected is None:
            continue
        if getattr(custom_field, attribute, None) != expected:
            return False
    return True


def _strip_values(model, db_alias: str, names) -> None:
    if not names:
        return
    pending = []
    rows = (
        model.objects.using(db_alias)
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
                # Re-check at strip time, not only during the earlier scan. A
                # writer that landed a value in between must not lose it.
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


def _holds_data(data: dict, key: str) -> bool:
    """True when `key` carries anything at all.

    Only `None` and the empty string count as blank. `custom_field_data` is raw
    JSON, so an integration can leave a list or an object in a field NetBox
    declares as text, and an empty one of those is still a value somebody
    stored. Since the whole point of this check is to refuse to destroy data we
    cannot account for, an unexpected shape reads as data, not as absence.
    """
    if key not in data:
        return False
    return data[key] not in (None, "")


def _names_holding_data(model, db_alias: str, names) -> set:
    """Return the subset of `names` that any row of `model` still has a value for.

    This is the guarantee the shape checks cannot give. `ui_editable="hidden"`
    stops NetBox's edit form, not its REST API, so a hidden field can still be
    the place an integration keeps data. Rather than try to prove provenance --
    NetBox records none, and every attribute an operator can reach is mutable --
    this asks the only question that actually matters before a destructive
    step: is anybody's data in here? A field holding a value anywhere is left
    alone in full, whoever wrote it.
    """
    if not names:
        return set()
    found: set = set()
    rows = (
        model.objects.using(db_alias)
        .only("pk", "custom_field_data")
        .iterator(chunk_size=_BATCH_SIZE)
    )
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


def _canonical_type_pks(ContentType, db_alias: str, definition) -> set:
    pks = set()
    for dotted_name in definition["object_types"]:
        content_type = _content_type(ContentType, db_alias, dotted_name)
        if content_type is not None:
            pks.add(content_type.pk)
    return pks


def _release_one_field(custom_field, definition, ContentType, db_alias: str) -> None:
    """Drop our own bindings, and the row itself if nothing else held it."""
    canonical = _canonical_type_pks(ContentType, db_alias, definition)
    bound = set(custom_field.object_types.values_list("pk", flat=True))
    if canonical:
        custom_field.object_types.remove(*canonical)
    if not (bound - canonical):
        custom_field.delete()


def _released_names_by_type() -> dict:
    released: dict = {}
    for definition in HARDWARE_CUSTOM_FIELD_DEFINITIONS:
        for dotted_name in definition["object_types"]:
            released.setdefault(dotted_name, set()).add(definition["name"])
    return released


def _populated_names(apps, db_alias: str, released_by_type: dict) -> set:
    populated: set = set()
    for app_label, model_name in AFFECTED_OBJECT_TYPES:
        names = released_by_type.get(f"{app_label}.{model_name}".lower())
        if not names:
            continue
        model = apps.get_model(app_label, model_name)
        populated |= _names_holding_data(model, db_alias, set(names))
    return populated


def remove_hardware_custom_fields(apps, schema_editor) -> None:
    """Release our bindings and delete the rows left with none.

    A field is touched only when it has our data type, is not operator-editable,
    and holds no value on any row. Anything else keeps its definition, its
    bindings and its values.
    """
    ContentType = apps.get_model("contenttypes", "ContentType")
    CustomField = apps.get_model("extras", "CustomField")
    db_alias = schema_editor.connection.alias

    definitions = {d["name"]: d for d in HARDWARE_CUSTOM_FIELD_DEFINITIONS}
    released_by_type = _released_names_by_type()
    skipped = _populated_names(apps, db_alias, released_by_type)

    # Lock the definitions for the rest of the transaction so their metadata
    # cannot be repurposed between the check and the delete, then re-read the
    # data under that lock: the scan above is an early exit, not the authority.
    locked = (
        CustomField.objects.using(db_alias)
        .filter(name__in=HARDWARE_CUSTOM_FIELD_NAMES)
        .select_for_update()
    )
    skipped |= _populated_names(apps, db_alias, released_by_type)

    for custom_field in locked:
        definition = definitions.get(custom_field.name)
        if definition is None or custom_field.name in skipped:
            continue
        if _is_ours(custom_field, definition):
            _release_one_field(custom_field, definition, ContentType, db_alias)
        else:
            skipped.add(custom_field.name)

    for app_label, model_name in AFFECTED_OBJECT_TYPES:
        names = released_by_type.get(f"{app_label}.{model_name}".lower())
        if names:
            names = names - skipped
        _strip_values(apps.get_model(app_label, model_name), db_alias, names)


def _may_rebind(apps, db_alias: str, custom_field, definition) -> bool:
    """Whether reverse may re-attach our binding to a row that already exists.

    Forward leaves no record of what it skipped, and shape alone cannot
    reconstruct it: a populated field of our exact shape whose canonical
    binding an operator had already removed looks identical to one forward
    released. Binding the first would expose somebody's data as a Proxbox
    field. So the emptiness test is applied again here -- a row still holding a
    value is never rebound, and a row forward released is empty by
    construction, so it still gets its binding back.
    """
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


def restore_hardware_custom_fields(apps, schema_editor) -> None:
    """Recreate a missing definition; leave an existing one's metadata alone."""
    ContentType = apps.get_model("contenttypes", "ContentType")
    CustomField = apps.get_model("extras", "CustomField")
    db_alias = schema_editor.connection.alias
    manager = CustomField.objects.using(db_alias)

    for definition in HARDWARE_CUSTOM_FIELD_DEFINITIONS:
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
            # Forward skipped this row, so reverse must not hand it a binding it
            # never had. Leave the operator's field exactly as it is.
            continue
        for content_type in object_types:
            custom_field.object_types.add(content_type)


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0086_remove_other_reflection_custom_fields"),
    ]

    operations = [
        migrations.RunPython(
            remove_hardware_custom_fields,
            reverse_code=restore_hardware_custom_fields,
        ),
    ]
