"""Execute migration 0087 -- the six fields 0086's label check refused.

0086 compared the label as evidence of ownership. Two writers inside this
project disagreed about the case of these six labels -- the plugin's own
`_v0_0_15_release_data` wrote sentence case, proxbox-api's inventory reconcile
rewrote them in title case -- so the check failed closed and left all six on
production. Failing closed was right; treating a label as ownership was not.
This migration compares the data type instead.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from typing import Any

import pytest

MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "netbox_proxbox"
    / "migrations"
    / "0087_remove_hardware_discovery_custom_fields.py"
)


def _install_stub() -> None:
    """Fill in only what is missing.

    A sibling migration test installs a wider stub into the same module slot,
    so this must add attributes rather than claim the slot -- whichever module
    imports first would otherwise leave the other one short an operation.
    """
    if "django" not in sys.modules:
        sys.modules["django"] = types.ModuleType("django")
    if "django.db" not in sys.modules:
        sys.modules["django.db"] = types.ModuleType("django.db")
    migrations = getattr(sys.modules["django.db"], "migrations", None)
    if migrations is None:
        migrations = types.ModuleType("django.db.migrations")
        sys.modules["django.db.migrations"] = migrations
        sys.modules["django.db"].migrations = migrations

    if not hasattr(migrations, "Migration"):

        class _Migration:
            dependencies: list = []
            operations: list = []

        migrations.Migration = _Migration
    if not hasattr(migrations, "RunPython"):
        migrations.RunPython = lambda code, reverse_code=None, **_k: (
            "RunPython",
            code,
        )
    if not hasattr(migrations, "RemoveField"):
        migrations.RemoveField = lambda **kwargs: ("RemoveField", kwargs)


@pytest.fixture
def migration():
    _install_stub()
    spec = importlib.util.spec_from_file_location("migration_0087", MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _CT:
    _pk = 1

    def __init__(self, app_label, model):
        self.app_label, self.model = app_label, model
        self.pk = _CT._pk
        _CT._pk += 1


class _DoesNotExist(Exception):
    pass


class _M2M:
    def __init__(self, members=None):
        self.members = list(members or [])
        self.added: list = []
        self.removed: list = []

    def add(self, *v):
        for x in v:
            self.added.append(x)
            if x not in self.members:
                self.members.append(x)

    def remove(self, *pks):
        self.removed.extend(sorted(pks))
        self.members = [m for m in self.members if m.pk not in set(pks)]

    def values_list(self, field, flat=False):
        return [m.pk for m in self.members]


class _CF:
    def __init__(self, name, **fields):
        self.name = name
        self.__dict__.update(fields)
        self.object_types = _M2M()
        self._store = None

    def delete(self):
        if self._store is not None:
            self._store.pop(self.name, None)


class _CFQS:
    def __init__(self, store, names):
        self._store, self._names = store, names
        self.locked = False

    def select_for_update(self):
        self.locked = True
        return self

    def __iter__(self):
        for name in list(self._names):
            field = self._store.get(name)
            if field is not None:
                field._store = self._store
                yield field


class _CFManager:
    def __init__(self, store):
        self._store = store
        self.last_queryset = None

    def using(self, _a):
        return self

    def filter(self, **kw):
        assert set(kw) == {"name__in"}
        self.last_queryset = _CFQS(
            self._store, [n for n in kw["name__in"] if n in self._store]
        )
        return self.last_queryset

    def get_or_create(self, *, name, defaults):
        existing = self._store.get(name)
        if existing is not None:
            return existing, False
        created = _CF(name, **defaults)
        self._store[name] = created
        return created, True

    def update_or_create(self, *, name, defaults):
        existing = self._store.get(name)
        if existing is not None:
            existing.__dict__.update(defaults)
            return existing, False
        created = _CF(name, **defaults)
        self._store[name] = created
        return created, True


class _Obj:
    def __init__(self, pk, data):
        self.pk, self.custom_field_data = pk, data


class _ObjManager:
    def __init__(self, rows):
        self.rows = rows
        self.bulk_updated: list = []
        self.select_for_update_calls = 0
        self.calls: list[str] = []

    def using(self, _a):
        return self

    def only(self, *_f):
        self.calls.append("only")
        return self

    def select_for_update(self):
        self.select_for_update_calls += 1
        self.calls.append("select_for_update")
        return self

    def iterator(self, chunk_size=None):
        self.calls.append("iterator")
        return iter(list(self.rows))

    def bulk_update(self, objs, fields, batch_size=None):
        self.calls.append("bulk_update")
        self.bulk_updated.extend(o.pk for o in objs)


class _CTManager:
    def __init__(self):
        self.by_name: dict = {}

    def using(self, _a):
        return self

    def get(self, **kw):
        key = f"{kw['app_label']}.{kw['model']}"
        return self.by_name.setdefault(key, _CT(kw["app_label"], kw["model"]))


class _Apps:
    def __init__(self, store=None, rows_by_model=None):
        self.store = {} if store is None else store
        self.cf_model = type("CustomField", (), {"objects": _CFManager(self.store)})
        self.obj_managers = {
            k: _ObjManager(v) for k, v in (rows_by_model or {}).items()
        }
        self.ct_manager = _CTManager()
        self.ct_model = type(
            "ContentType",
            (),
            {"objects": self.ct_manager, "DoesNotExist": _DoesNotExist},
        )

    def get_model(self, app_label, model_name):
        if (app_label, model_name) == ("extras", "CustomField"):
            return self.cf_model
        if (app_label, model_name) == ("contenttypes", "ContentType"):
            return self.ct_model
        manager = self.obj_managers.setdefault((app_label, model_name), _ObjManager([]))
        return type(model_name, (), {"objects": manager})


class _Schema:
    class connection:
        alias = "default"


# Read from the production registry, not from the migration under test, so a
# definition-table edit cannot quietly move the goalposts. Shape: name -> (type,
# label, ui_editable, dotted content type).
PRODUCTION_FIELDS = {
    "hardware_chassis_manufacturer": (
        "text",
        "Chassis Manufacturer",
        "hidden",
        "dcim.device",
    ),
    "hardware_chassis_product": ("text", "Chassis Product", "hidden", "dcim.device"),
    "hardware_chassis_serial": ("text", "Chassis Serial", "hidden", "dcim.device"),
    "nic_duplex": ("text", "NIC Duplex", "hidden", "dcim.interface"),
    "nic_link": ("boolean", "NIC Link Up", "hidden", "dcim.interface"),
    "nic_speed_gbps": ("integer", "NIC Speed (Gbps)", "hidden", "dcim.interface"),
}

# What this plugin's own _v0_0_15_release_data migration wrote. It disagrees
# with production on the label of every field and on the description of the
# chassis manufacturer, which is why 0086's label check refused all six.
LEGACY_LABELS = {
    "hardware_chassis_manufacturer": "Chassis manufacturer",
    "hardware_chassis_product": "Chassis product name",
    "hardware_chassis_serial": "Chassis serial",
    "nic_duplex": "NIC duplex",
    "nic_link": "NIC link up",
    "nic_speed_gbps": "NIC speed (Gbps)",
}


def _seed(apps, *, labels=None):
    """Build the six fields as production carries them, with real bindings."""
    labels = labels or {}
    store = apps.store
    for name, (type_, label, ui_editable, dotted) in PRODUCTION_FIELDS.items():
        app_label, model = dotted.split(".")
        field = _CF(
            name,
            type=type_,
            label=labels.get(name, label),
            ui_editable=ui_editable,
        )
        field.object_types.members.append(
            apps.ct_manager.get(app_label=app_label, model=model)
        )
        store[name] = field
    # NetBox keeps a key for every defined custom field, so an unpopulated
    # field is present with a null value -- exactly what production carries for
    # all six. A null key is stale metadata to strip; it is not data.
    rows = {
        ("dcim", "Device"): [
            _Obj(
                1,
                {n: None for n in PRODUCTION_FIELDS}
                | {"cf_hardware_chassis_serial": None, "keep": "mine"},
            ),
            _Obj(2, None),
        ],
        ("dcim", "Interface"): [
            _Obj(3, {n: None for n in PRODUCTION_FIELDS} | {"keep": "mine"}),
        ],
    }
    for key, value in rows.items():
        apps.obj_managers[key] = _ObjManager(value)
    return store, rows


def test_all_six_are_removed_despite_the_labels_that_blocked_0086(migration):
    """The legacy labels 0086 expected must no longer keep a field alive."""
    apps = _Apps()
    store, rows = _seed(apps, labels=LEGACY_LABELS)

    migration.remove_hardware_custom_fields(apps, _Schema())

    assert store == {}, (
        "every one of the six must go; 0086 left them because it compared the "
        "label, and this plugin's two writers spell these labels differently"
    )
    device = rows[("dcim", "Device")][0]
    assert "hardware_chassis_serial" not in device.custom_field_data
    assert "cf_hardware_chassis_serial" not in device.custom_field_data
    assert device.custom_field_data["keep"] == "mine"
    assert rows[("dcim", "Device")][1].custom_field_data is None
    assert apps.obj_managers[("dcim", "Device")].bulk_updated == [1], (
        "and the change must be written back, not only mutated in memory"
    )
    assert apps.obj_managers[("dcim", "Interface")].bulk_updated == [3]


def test_production_labels_are_removed_too(migration):
    """The same must hold for the labels production actually carries."""
    apps = _Apps()
    store, _rows = _seed(apps)

    migration.remove_hardware_custom_fields(apps, _Schema())

    assert store == {}


def test_a_field_whose_type_differs_is_still_left_alone(migration):
    """Type remains real evidence: a different type is a different field."""
    apps = _Apps()
    store, rows = _seed(apps)
    store["nic_link"].type = "text"  # ours is boolean

    migration.remove_hardware_custom_fields(apps, _Schema())

    assert "nic_link" in store, "a field of a different type is not ours"
    assert store["nic_link"].object_types.removed == []
    assert "nic_link" in rows[("dcim", "Interface")][0].custom_field_data, (
        "and its key must survive with it"
    )
    assert "nic_duplex" not in store


def test_a_repurposed_field_of_our_own_type_is_left_alone(migration):
    """An operator who took the name over made it writable; that is the tell."""
    apps = _Apps()
    store, rows = _seed(apps)
    store["nic_duplex"].ui_editable = "yes"

    migration.remove_hardware_custom_fields(apps, _Schema())

    assert "nic_duplex" in store, (
        "same name and same type is not enough to delete: an editable field is "
        "one somebody is keeping their own data in"
    )
    assert store["nic_duplex"].object_types.removed == []
    assert "nic_duplex" in rows[("dcim", "Interface")][0].custom_field_data
    assert "nic_link" not in store, "the untouched fields still go"


def test_forward_is_idempotent(migration):
    apps = _Apps()
    store, rows = _seed(apps)
    migration.remove_hardware_custom_fields(apps, _Schema())
    snapshot = {
        k: [dict(r.custom_field_data or {}) for r in v] for k, v in rows.items()
    }
    migration.remove_hardware_custom_fields(apps, _Schema())
    assert store == {}
    assert {
        k: [dict(r.custom_field_data or {}) for r in v] for k, v in rows.items()
    } == snapshot


def test_reverse_recreates_all_six_with_production_metadata(migration):
    """A rollback must restore what production held, not NetBox defaults."""
    apps = _Apps()
    migration.restore_hardware_custom_fields(apps, _Schema())

    assert set(apps.store) == set(PRODUCTION_FIELDS)
    for name, (type_, label, ui_editable, dotted) in PRODUCTION_FIELDS.items():
        field = apps.store[name]
        assert (field.type, field.label, field.ui_editable) == (
            type_,
            label,
            ui_editable,
        )
        assert field.ui_visible == "if-set"
        assert field.weight == 300
        assert field.filter_logic == "loose"
        assert field.required is False
        assert field.search_weight == 1000
        assert field.group_name == "Proxmox"
        assert field.description
        app_label, model = dotted.split(".")
        assert [(c.app_label, c.model) for c in field.object_types.added] == [
            (app_label, model)
        ]


def test_a_field_also_bound_elsewhere_keeps_its_row_and_that_binding(migration):
    """Releasing our binding must not delete somebody else's field."""
    apps = _Apps()
    store, rows = _seed(apps)
    canonical = store["nic_duplex"].object_types.members[0]
    foreign = _CT("tenancy", "tenant")
    store["nic_duplex"].object_types.members.append(foreign)

    migration.remove_hardware_custom_fields(apps, _Schema())

    assert "nic_duplex" in store, "a row with a binding we did not create survives"
    assert store["nic_duplex"].object_types.members == [foreign], (
        "our own binding is released and only the foreign one is kept"
    )
    assert canonical.pk in store["nic_duplex"].object_types.removed
    assert "nic_link" not in store


def test_a_skipped_field_is_untouched_by_a_rollback(migration):
    """Reverse must not hand an operator's field a binding it never had."""
    apps = _Apps()
    store, rows = _seed(apps)
    store["nic_duplex"].ui_editable = "yes"
    store["nic_duplex"].label = "Operator label"
    migration.remove_hardware_custom_fields(apps, _Schema())

    migration.restore_hardware_custom_fields(apps, _Schema())

    operator_field = store["nic_duplex"]
    assert operator_field.label == "Operator label"
    assert operator_field.ui_editable == "yes"
    assert operator_field.object_types.added == [], (
        "a row forward skipped must gain no Proxbox binding on rollback"
    )
    assert set(store) == set(PRODUCTION_FIELDS), "the other five come back"


def test_reverse_does_not_overwrite_an_operator_owned_field(migration):
    """A field that already exists keeps its own metadata."""
    apps = _Apps(
        {
            "nic_duplex": _CF(
                "nic_duplex", type="text", ui_editable="hidden", label="Operator label"
            )
        }
    )

    migration.restore_hardware_custom_fields(apps, _Schema())

    assert apps.store["nic_duplex"].label == "Operator label", (
        "recreating a definition must not rewrite one somebody else owns"
    )
    assert set(apps.store) == set(PRODUCTION_FIELDS)


def test_a_field_holding_data_is_left_completely_alone(migration):
    """The gate that does not depend on guessing who owns the field.

    `ui_editable="hidden"` stops NetBox's edit form, not its REST API, so an
    integration can populate a hidden field of our exact type. Shape alone
    cannot tell that apart from ours. Holding a value can, and does.
    """
    apps = _Apps()
    store, rows = _seed(apps)
    rows[("dcim", "Interface")][0].custom_field_data["nic_duplex"] = "full"

    migration.remove_hardware_custom_fields(apps, _Schema())

    assert "nic_duplex" in store, "a field somebody's data is in is never deleted"
    assert store["nic_duplex"].object_types.removed == [], (
        "and it keeps the binding that makes the data reachable"
    )
    assert rows[("dcim", "Interface")][0].custom_field_data["nic_duplex"] == "full"
    assert "nic_link" not in store, "the empty ones still go"


def test_a_legacy_prefixed_value_also_protects_the_field(migration):
    """The historical `cf_` spelling is data too."""
    apps = _Apps()
    store, rows = _seed(apps)
    rows[("dcim", "Device")][0].custom_field_data["cf_hardware_chassis_serial"] = "SN1"

    migration.remove_hardware_custom_fields(apps, _Schema())

    assert "hardware_chassis_serial" in store
    assert (
        rows[("dcim", "Device")][0].custom_field_data["cf_hardware_chassis_serial"]
        == "SN1"
    )
    assert "hardware_chassis_product" not in store


def test_an_empty_container_is_data(migration):
    """`custom_field_data` is raw JSON; an unexpected shape reads as data."""
    apps = _Apps()
    store, rows = _seed(apps)
    rows[("dcim", "Device")][0].custom_field_data["hardware_chassis_serial"] = []
    rows[("dcim", "Interface")][0].custom_field_data["nic_duplex"] = {}

    migration.remove_hardware_custom_fields(apps, _Schema())

    assert "hardware_chassis_serial" in store, (
        "an empty list is still something an integration stored"
    )
    assert "nic_duplex" in store
    assert (
        rows[("dcim", "Device")][0].custom_field_data["hardware_chassis_serial"] == []
    )
    assert rows[("dcim", "Interface")][0].custom_field_data["nic_duplex"] == {}
    assert "nic_link" not in store, "the genuinely blank ones still go"


def test_an_empty_string_is_not_data(migration):
    """A blank is what an untouched text field looks like, not a value."""
    apps = _Apps()
    store, rows = _seed(apps)
    rows[("dcim", "Device")][0].custom_field_data["hardware_chassis_serial"] = ""

    migration.remove_hardware_custom_fields(apps, _Schema())

    assert store == {}


def test_data_on_a_later_row_still_protects_the_field(migration):
    """The scan must read every row, not stop at the first clean one."""
    apps = _Apps()
    store, rows = _seed(apps)
    interfaces = rows[("dcim", "Interface")]
    for pk in range(4, 9):
        interfaces.append(_Obj(pk, {n: None for n in PRODUCTION_FIELDS}))
    interfaces.append(
        _Obj(9, {n: None for n in PRODUCTION_FIELDS} | {"nic_link": True})
    )
    apps.obj_managers[("dcim", "Interface")] = _ObjManager(interfaces)

    migration.remove_hardware_custom_fields(apps, _Schema())

    assert "nic_link" in store, (
        "a value anywhere protects the field, however deep in the table it sits"
    )
    assert interfaces[-1].custom_field_data["nic_link"] is True
    assert "nic_duplex" not in store, "the empty ones still go"


def test_the_definitions_are_locked_before_anything_is_deleted(migration):
    """The early scan is an exit, not the authority; the delete runs locked."""
    apps = _Apps()
    _store, _rows = _seed(apps)

    migration.remove_hardware_custom_fields(apps, _Schema())

    assert apps.cf_model.objects.last_queryset.locked, (
        "metadata must not be repurposeable between the check and the delete"
    )


def test_a_value_written_after_the_scan_is_not_stripped(migration):
    """Re-check at strip time, so a late writer does not lose its value."""
    apps = _Apps()
    store, rows = _seed(apps)
    device = rows[("dcim", "Device")][0]

    real_release = migration._release_one_field

    def _land_a_late_write(custom_field, definition, ContentType, db_alias):
        device.custom_field_data["hardware_chassis_product"] = "written late"
        return real_release(custom_field, definition, ContentType, db_alias)

    migration._release_one_field = _land_a_late_write
    try:
        migration.remove_hardware_custom_fields(apps, _Schema())
    finally:
        migration._release_one_field = real_release

    assert device.custom_field_data["hardware_chassis_product"] == "written late", (
        "a value that landed after the scan must survive the strip"
    )
    assert "hardware_chassis_serial" not in device.custom_field_data


def test_reverse_does_not_rebind_a_populated_field_of_our_own_shape(migration):
    """The case shape alone cannot tell apart from one forward released."""
    apps = _Apps()
    store, rows = _seed(apps)
    # Our exact shape, holding somebody's data, with our binding already gone.
    field = store["nic_duplex"]
    field.object_types.members.clear()
    rows[("dcim", "Interface")][0].custom_field_data["nic_duplex"] = "full"
    migration.remove_hardware_custom_fields(apps, _Schema())

    migration.restore_hardware_custom_fields(apps, _Schema())

    assert field.object_types.added == [], (
        "rollback must not expose an integration's data as a Proxbox field"
    )
    assert rows[("dcim", "Interface")][0].custom_field_data["nic_duplex"] == "full"


def test_reverse_still_rebinds_a_field_forward_released(migration):
    """An empty survivor keeps full rollback fidelity."""
    apps = _Apps()
    store, rows = _seed(apps)
    foreign = _CT("tenancy", "tenant")
    store["nic_duplex"].object_types.members.append(foreign)
    migration.remove_hardware_custom_fields(apps, _Schema())
    assert "nic_duplex" in store

    migration.restore_hardware_custom_fields(apps, _Schema())

    assert [(c.app_label, c.model) for c in store["nic_duplex"].object_types.added] == [
        ("dcim", "interface")
    ]


def test_a_value_written_before_the_lock_is_caught_by_the_rescan(migration):
    """The scan is repeated once the definitions are locked, and that matters."""
    apps = _Apps()
    store, rows = _seed(apps)
    interface = rows[("dcim", "Interface")][0]

    original = _CFQS.select_for_update

    def _land_a_write_while_locking(self):
        interface.custom_field_data["nic_duplex"] = "full"
        return original(self)

    _CFQS.select_for_update = _land_a_write_while_locking
    try:
        migration.remove_hardware_custom_fields(apps, _Schema())
    finally:
        _CFQS.select_for_update = original

    assert "nic_duplex" in store, (
        "a value that landed after the early scan must still protect the field"
    )
    assert interface.custom_field_data["nic_duplex"] == "full"
    assert "nic_link" not in store
