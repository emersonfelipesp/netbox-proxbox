"""Execute migration 0086 against a behavior-recording fake apps registry."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATION_PATH = (
    REPO_ROOT
    / "netbox_proxbox"
    / "migrations"
    / "0086_remove_other_reflection_custom_fields.py"
)

EXPECTED_NAMES = {
    "hardware_chassis_manufacturer",
    "hardware_chassis_product",
    "hardware_chassis_serial",
    "nic_duplex",
    "nic_link",
    "nic_speed_gbps",
    "proxmox_cluster_id",
    "proxmox_cluster_name",
    "proxmox_cluster_status",
    "proxmox_interface",
    "proxmox_ip_addresses",
    "proxmox_mac",
    "proxmox_vlan_id",
    "proxbox_bridge",
    "proxbox_storage_id",
    "proxmox_cluster",
    "proxmox_cpu_type",
    "proxmox_device_names",
    "proxmox_disk",
    "proxmox_interfaces",
    "proxmox_link",
    "proxmox_notes",
    "proxmox_os",
    "proxmox_storage_ids",
    "proxmox_storage_names",
    "proxmox_tags",
    "proxmox_tcp_states",
    "proxmox_vmid",
    "proxbox_last_run_id",
    "proxmox_last_updated",
}

OUT_OF_SCOPE = (
    "proxmox_node",
    "proxmox_storage",
    "proxmox_iso",
    "proxmox_template_vmid",
    "cloud_init_user",
    "cloud_init_ssh_keys",
    "cloud_init_user_data",
    "cloud_init_network",
    "proxbox_intent_state",
    "proxbox_last_apply_run_id",
    "apply_to_proxmox",
    "apply_destroy_confirmed",
    "source_packer_template",
    "listen_address",
    "nginx_main_config_path",
    "nginx_systemd_unit",
)

EXPECTED_AFFECTED_TYPES = (
    ("dcim", "Device"),
    ("dcim", "Interface"),
    ("dcim", "Manufacturer"),
    ("dcim", "Site"),
    ("dcim", "DeviceRole"),
    ("dcim", "DeviceType"),
    ("ipam", "IPAddress"),
    ("ipam", "VLAN"),
    ("virtualization", "Cluster"),
    ("virtualization", "ClusterGroup"),
    ("virtualization", "ClusterType"),
    ("virtualization", "VirtualMachine"),
    ("virtualization", "VirtualDisk"),
    ("virtualization", "VMInterface"),
)

EXPECTED_BINDINGS = {
    "hardware_chassis_manufacturer": {"dcim.device"},
    "hardware_chassis_product": {"dcim.device"},
    "hardware_chassis_serial": {"dcim.device"},
    "nic_duplex": {"dcim.interface"},
    "nic_link": {"dcim.interface"},
    "nic_speed_gbps": {"dcim.interface"},
    "proxmox_cluster_id": {"virtualization.cluster"},
    "proxmox_cluster_name": {
        "virtualization.cluster",
        "virtualization.clustergroup",
    },
    "proxmox_cluster_status": {
        "virtualization.cluster",
        "virtualization.clustergroup",
    },
    "proxmox_interface": {"ipam.ipaddress"},
    "proxmox_ip_addresses": {"ipam.ipaddress"},
    "proxmox_mac": {"ipam.ipaddress"},
    "proxmox_vlan_id": {"ipam.vlan"},
    "proxbox_bridge": {"virtualization.vminterface"},
    "proxbox_storage_id": {"virtualization.virtualdisk"},
    "proxmox_cluster": {"dcim.device", "virtualization.virtualmachine"},
    "proxmox_cpu_type": {"dcim.device", "virtualization.virtualmachine"},
    "proxmox_device_names": {"dcim.device", "virtualization.virtualmachine"},
    "proxmox_disk": {"dcim.device", "virtualization.virtualmachine"},
    "proxmox_interfaces": {"dcim.device", "virtualization.virtualmachine"},
    "proxmox_link": {"dcim.device", "virtualization.virtualmachine"},
    "proxmox_notes": {"dcim.device", "virtualization.virtualmachine"},
    "proxmox_os": {"dcim.device", "virtualization.virtualmachine"},
    "proxmox_storage_ids": {"dcim.device", "virtualization.virtualmachine"},
    "proxmox_storage_names": {"dcim.device", "virtualization.virtualmachine"},
    "proxmox_tags": {"dcim.device", "virtualization.virtualmachine"},
    "proxmox_tcp_states": {"dcim.device", "virtualization.virtualmachine"},
    "proxmox_vmid": {"dcim.device", "virtualization.virtualmachine"},
    "proxbox_last_run_id": {
        "dcim.device",
        "virtualization.cluster",
        "virtualization.virtualmachine",
    },
    "proxmox_last_updated": {
        "dcim.device",
        "dcim.devicerole",
        "dcim.devicetype",
        "dcim.interface",
        "dcim.manufacturer",
        "dcim.site",
        "ipam.ipaddress",
        "ipam.vlan",
        "virtualization.cluster",
        "virtualization.clustertype",
        "virtualization.virtualdisk",
        "virtualization.virtualmachine",
        "virtualization.vminterface",
    },
}

EXPECTED_HARDWARE_DEFINITIONS = {
    "hardware_chassis_serial": (
        "text",
        "Chassis serial",
        "Chassis serial number reported by dmidecode -t 3 during SSH-based "
        "hardware discovery. Populated automatically by Proxbox when enabled.",
    ),
    "hardware_chassis_manufacturer": (
        "text",
        "Chassis manufacturer",
        "Chassis manufacturer string reported by dmidecode -t 1 during "
        "SSH-based hardware discovery.",
    ),
    "hardware_chassis_product": (
        "text",
        "Chassis product name",
        "Chassis product / model name reported by dmidecode -t 1 during "
        "SSH-based hardware discovery.",
    ),
    "nic_speed_gbps": (
        "integer",
        "NIC speed (Gbps)",
        "Negotiated NIC link speed in Gbps, parsed from ethtool output during "
        "SSH-based hardware discovery.",
    ),
    "nic_duplex": (
        "text",
        "NIC duplex",
        "Negotiated NIC duplex mode (full/half/unknown), parsed from ethtool "
        "output during SSH-based hardware discovery.",
    ),
    "nic_link": (
        "boolean",
        "NIC link up",
        "Whether the NIC reports link up, parsed from ethtool output during "
        "SSH-based hardware discovery.",
    ),
}


def _install_django_migrations_stub() -> None:
    if "django" not in sys.modules:
        sys.modules["django"] = types.ModuleType("django")
    if "django.db" not in sys.modules:
        sys.modules["django.db"] = types.ModuleType("django.db")
    if not hasattr(sys.modules["django.db"], "migrations"):
        stub = types.ModuleType("django.db.migrations")

        class _Migration:
            dependencies: list = []
            operations: list = []

        stub.Migration = _Migration
        stub.RunPython = lambda code, reverse_code=None: (
            "RunPython",
            code,
            reverse_code,
        )
        stub.RemoveField = lambda **kwargs: ("RemoveField", kwargs)
        sys.modules["django.db.migrations"] = stub
        sys.modules["django.db"].migrations = stub


def _load_migration():
    _install_django_migrations_stub()
    spec = importlib.util.spec_from_file_location("migration_0086", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeM2M:
    """Models real membership, not just calls.

    The migration decides whether a definition may be deleted by comparing the
    bindings it finds against the ones Proxbox itself created, so a fake that
    only records `add()` calls cannot exercise that decision at all -- it would
    let an over-broad deletion pass.
    """

    def __init__(self, members: "list[_FakeContentType] | None" = None) -> None:
        self.added: list[_FakeContentType] = []
        self.removed: list[int] = []
        self.members: list[_FakeContentType] = list(members or [])

    def add(self, *values: "_FakeContentType") -> None:
        for value in values:
            self.added.append(value)
            if value not in self.members:
                self.members.append(value)

    def remove(self, *pks: int) -> None:
        wanted = set(pks)
        self.removed.extend(sorted(wanted))
        self.members = [m for m in self.members if m.pk not in wanted]

    def values_list(self, field: str, flat: bool = False):
        assert field == "pk" and flat is True
        return [m.pk for m in self.members]


class _FakeCustomField:
    def __init__(self, name: str, **fields: Any) -> None:
        self.name = name
        self.__dict__.update(fields)
        self.object_types = _FakeM2M()
        self.deleted = False
        self._store: dict[str, "_FakeCustomField"] | None = None

    def delete(self) -> None:
        self.deleted = True
        if self._store is not None:
            self._store.pop(self.name, None)


class _CustomFieldQuerySet:
    def __init__(self, store: dict[str, _FakeCustomField], names: list[str]) -> None:
        self._store = store
        self._names = names

    def __iter__(self):
        for name in list(self._names):
            field = self._store.get(name)
            if field is not None:
                field._store = self._store
                yield field

    def delete(self) -> tuple[int, dict[str, int]]:
        for name in self._names:
            self._store.pop(name, None)
        return len(self._names), {}


class _CustomFieldManager:
    def __init__(self, store: dict[str, _FakeCustomField]) -> None:
        self._store = store

    def using(self, _alias: str) -> "_CustomFieldManager":
        return self

    def filter(self, **kwargs: Any) -> _CustomFieldQuerySet:
        assert set(kwargs) == {"name__in"}, f"unexpected delete predicate: {kwargs}"
        assert set(kwargs["name__in"]) == EXPECTED_NAMES
        wanted = [name for name in kwargs["name__in"] if name in self._store]
        return _CustomFieldQuerySet(self._store, wanted)

    def get_or_create(
        self, *, name: str, defaults: dict[str, Any]
    ) -> tuple[_FakeCustomField, bool]:
        """Existing rows keep their own definition -- that is the contract.

        A field that survived the forward pass is the operator's, so a rollback
        must not overwrite its metadata with ours. Modelling that here is what
        lets the reverse test catch a regression to `update_or_create`.
        """
        existing = self._store.get(name)
        if existing is not None:
            return existing, False
        created = _FakeCustomField(name, **defaults)
        self._store[name] = created
        return created, True

    def update_or_create(
        self, *, name: str, defaults: dict[str, Any]
    ) -> tuple[_FakeCustomField, bool]:
        existing = self._store.get(name)
        if existing is not None:
            existing.__dict__.update(defaults)
            return existing, False
        created = _FakeCustomField(name, **defaults)
        self._store[name] = created
        return created, True


class _FakeObject:
    def __init__(self, pk: int, custom_field_data: Any) -> None:
        self.pk = pk
        self.custom_field_data = custom_field_data


class _ObjectManager:
    def __init__(self, rows: list[_FakeObject]) -> None:
        self.rows = rows
        self.bulk_updated: list[int] = []

    def using(self, _alias: str) -> "_ObjectManager":
        return self

    def only(self, *_fields: str) -> "_ObjectManager":
        return self

    def iterator(self, chunk_size: int | None = None):
        assert chunk_size == 500
        return iter(list(self.rows))

    def bulk_update(self, objs: Any, fields: Any, batch_size: int | None = None):
        materialized = list(objs)
        assert tuple(fields) == ("custom_field_data",)
        assert batch_size == 500
        self.bulk_updated.extend(obj.pk for obj in materialized)
        return len(materialized)


class _FakeContentType:
    _next_pk = 1

    def __init__(self, app_label: str, model: str) -> None:
        self.app_label = app_label
        self.model = model
        self.pk = _FakeContentType._next_pk
        _FakeContentType._next_pk += 1

    @property
    def dotted_name(self) -> str:
        return f"{self.app_label}.{self.model}"


class _ContentTypeDoesNotExist(Exception):
    pass


class _ContentTypeManager:
    def __init__(self, missing: set[str] | None = None) -> None:
        self.missing = missing or set()
        self.by_name: dict[str, _FakeContentType] = {}

    def using(self, _alias: str) -> "_ContentTypeManager":
        return self

    def get(self, **kwargs: Any) -> _FakeContentType:
        assert set(kwargs) == {"app_label", "model"}
        dotted_name = f"{kwargs['app_label']}.{kwargs['model']}"
        if dotted_name in self.missing:
            raise _ContentTypeDoesNotExist()
        return self.by_name.setdefault(
            dotted_name,
            _FakeContentType(kwargs["app_label"], kwargs["model"]),
        )


class _FakeApps:
    def __init__(
        self,
        migration,
        custom_fields: dict[str, _FakeCustomField],
        rows_by_model: dict[tuple[str, str], list[_FakeObject]],
        *,
        missing_content_types: set[str] | None = None,
    ) -> None:
        self.custom_field_store = custom_fields
        self.custom_field_model = type(
            "CustomField", (), {"objects": _CustomFieldManager(custom_fields)}
        )
        self.object_managers = {
            key: _ObjectManager(rows) for key, rows in rows_by_model.items()
        }
        self.object_models = {
            key: type(key[1], (), {"objects": manager})
            for key, manager in self.object_managers.items()
        }
        self.content_type_manager = _ContentTypeManager(missing_content_types)
        self.content_type_model = type(
            "ContentType",
            (),
            {
                "objects": self.content_type_manager,
                "DoesNotExist": _ContentTypeDoesNotExist,
            },
        )

    def get_model(self, app_label: str, model_name: str):
        key = (app_label, model_name)
        if key == ("extras", "CustomField"):
            return self.custom_field_model
        if key == ("contenttypes", "ContentType"):
            return self.content_type_model
        if key in self.object_models:
            return self.object_models[key]
        raise AssertionError(f"migration touched an unexpected model: {key}")


class _FakeSchemaEditor:
    class connection:  # noqa: N801 - mirrors Django's attribute path
        alias = "default"


@pytest.fixture
def migration():
    return _load_migration()


def _seed(migration):
    # Seeded with the metadata Proxbox itself wrote. The migration proves
    # ownership by comparing it, so a bare fake would read as somebody else's
    # field and be skipped entirely -- which is the correct behaviour, and
    # exactly why the seed has to model a real installation.
    canonical = {
        definition["name"]: definition
        for definition in migration.OTHER_REFLECTION_CUSTOM_FIELD_DEFINITIONS
    }
    store = {}
    for name in EXPECTED_NAMES | set(OUT_OF_SCOPE):
        definition = canonical.get(name, {})
        store[name] = _FakeCustomField(
            name,
            type=definition.get("type"),
            label=definition.get("label"),
        )
    rows_by_model = {}
    for index, key in enumerate(EXPECTED_AFFECTED_TYPES, start=1):
        survivor_values = {
            name: {"field": name, "model": ".".join(key)} for name in OUT_OF_SCOPE
        }
        rows_by_model[key] = [
            _FakeObject(
                index * 10 + 1,
                {
                    **{name: f"stale-{name}" for name in EXPECTED_NAMES},
                    **survivor_values,
                    "operator_field": ["preserve", index],
                },
            ),
            _FakeObject(index * 10 + 2, {"operator_field": ["untouched", index]}),
            _FakeObject(index * 10 + 3, None),
        ]
    return store, rows_by_model


def test_forward_deletes_exactly_thirty_and_spares_every_out_of_scope_name(
    migration,
) -> None:
    store, rows_by_model = _seed(migration)
    apps = _FakeApps(migration, store, rows_by_model)

    migration.remove_other_reflection_custom_fields(apps, _FakeSchemaEditor())

    assert EXPECTED_NAMES == set(migration.OTHER_REFLECTION_CUSTOM_FIELD_NAMES)
    assert len(migration.OTHER_REFLECTION_CUSTOM_FIELD_NAMES) == 30
    assert EXPECTED_NAMES.isdisjoint(store)
    for name in OUT_OF_SCOPE:
        assert name in store, f"{name} must survive migration 0086"


def test_forward_strips_stale_keys_from_every_type_and_preserves_values(
    migration,
) -> None:
    store, rows_by_model = _seed(migration)
    apps = _FakeApps(migration, store, rows_by_model)

    migration.remove_other_reflection_custom_fields(apps, _FakeSchemaEditor())

    assert tuple(migration.AFFECTED_OBJECT_TYPES) == EXPECTED_AFFECTED_TYPES

    # Stripping is per binding, not per name. A field is released only from the
    # object types Proxbox itself bound it to; anywhere else its values are the
    # operator's and the reverse cannot restore JSON, so they must survive.
    released_by_type: dict[str, set[str]] = {}
    for definition in migration.OTHER_REFLECTION_CUSTOM_FIELD_DEFINITIONS:
        for dotted_name in definition["object_types"]:
            released_by_type.setdefault(dotted_name, set()).add(definition["name"])

    for index, key in enumerate(EXPECTED_AFFECTED_TYPES, start=1):
        first, untouched, null = rows_by_model[key]
        # Content-type labels are lowercase; AFFECTED_OBJECT_TYPES carries
        # model class names. Folding here is deliberate -- the migration has to
        # do the same, and forgetting to strips nothing at all.
        dotted = ".".join(key).lower()
        released = released_by_type.get(dotted, set())
        assert released, f"{dotted} should have at least one released name"
        assert released.isdisjoint(first.custom_field_data), (
            f"names Proxbox bound to {dotted} must be stripped there"
        )
        for name in EXPECTED_NAMES - released:
            assert name in first.custom_field_data, (
                f"{name} is not bound to {dotted} by Proxbox, so its value there "
                "belongs to whoever wrote it and must not be removed"
            )
        for name in OUT_OF_SCOPE:
            assert first.custom_field_data[name] == {
                "field": name,
                "model": ".".join(key),
            }
        assert first.custom_field_data["operator_field"] == ["preserve", index]
        assert untouched.custom_field_data == {"operator_field": ["untouched", index]}
        assert null.custom_field_data is None
        assert apps.object_managers[key].bulk_updated == [first.pk]


def test_forward_is_idempotent(migration) -> None:
    store, rows_by_model = _seed(migration)
    apps = _FakeApps(migration, store, rows_by_model)
    migration.remove_other_reflection_custom_fields(apps, _FakeSchemaEditor())
    first_pass = {
        key: [
            dict(row.custom_field_data) if row.custom_field_data else None
            for row in rows
        ]
        for key, rows in rows_by_model.items()
    }
    writes = {
        key: list(manager.bulk_updated) for key, manager in apps.object_managers.items()
    }

    migration.remove_other_reflection_custom_fields(apps, _FakeSchemaEditor())

    assert {
        key: [
            dict(row.custom_field_data) if row.custom_field_data else None
            for row in rows
        ]
        for key, rows in rows_by_model.items()
    } == first_pass
    assert {
        key: manager.bulk_updated for key, manager in apps.object_managers.items()
    } == writes


def test_reverse_restores_all_definitions_and_original_bindings(migration) -> None:
    store: dict[str, _FakeCustomField] = {}
    rows_by_model = {key: [] for key in EXPECTED_AFFECTED_TYPES}
    apps = _FakeApps(migration, store, rows_by_model)

    migration.restore_other_reflection_custom_fields(apps, _FakeSchemaEditor())

    assert set(store) == EXPECTED_NAMES
    definitions = {
        definition["name"]: definition
        for definition in migration.OTHER_REFLECTION_CUSTOM_FIELD_DEFINITIONS
    }
    assert set(definitions) == EXPECTED_NAMES
    for name, field in store.items():
        definition = definitions[name]
        assert field.type == definition["type"]
        assert field.label == definition["label"]
        assert field.description == definition["description"]
        assert field.ui_visible == definition["ui_visible"]
        assert field.ui_editable == definition["ui_editable"]
        assert field.group_name == definition["group_name"]
        assert {
            content_type.dotted_name for content_type in field.object_types.added
        } == (EXPECTED_BINDINGS[name])
    assert store["proxbox_storage_id"].related_object_type.dotted_name == (
        "netbox_proxbox.proxmoxstorage"
    )
    assert store["proxbox_bridge"].related_object_type.dotted_name == "dcim.interface"


def test_reverse_uses_the_original_hardware_migration_definitions(migration) -> None:
    store: dict[str, _FakeCustomField] = {}
    rows_by_model = {key: [] for key in EXPECTED_AFFECTED_TYPES}
    apps = _FakeApps(migration, store, rows_by_model)

    migration.restore_other_reflection_custom_fields(apps, _FakeSchemaEditor())

    for name, expected in EXPECTED_HARDWARE_DEFINITIONS.items():
        field = store[name]
        assert (field.type, field.label, field.description) == expected
        assert field.ui_visible == "always"
        assert field.ui_editable == "hidden"
        assert field.filter_logic == "disabled"
        assert field.required is False
        assert field.search_weight == 0
        assert field.group_name == ""


def test_reverse_skips_a_missing_content_type_without_failing(migration) -> None:
    store: dict[str, _FakeCustomField] = {}
    rows_by_model = {key: [] for key in EXPECTED_AFFECTED_TYPES}
    apps = _FakeApps(
        migration,
        store,
        rows_by_model,
        missing_content_types={"virtualization.clustergroup"},
    )

    migration.restore_other_reflection_custom_fields(apps, _FakeSchemaEditor())

    assert set(store) == EXPECTED_NAMES
    assert {
        content_type.dotted_name
        for content_type in store["proxmox_cluster_name"].object_types.added
    } == {"virtualization.cluster"}


def test_reverse_does_not_create_a_field_when_every_binding_is_missing(
    migration,
) -> None:
    store: dict[str, _FakeCustomField] = {}
    rows_by_model = {key: [] for key in EXPECTED_AFFECTED_TYPES}
    apps = _FakeApps(
        migration,
        store,
        rows_by_model,
        missing_content_types={"virtualization.virtualdisk"},
    )

    migration.restore_other_reflection_custom_fields(apps, _FakeSchemaEditor())

    assert "proxbox_storage_id" not in store
    assert "proxmox_last_updated" in store


def test_migration_depends_on_the_vm_reflection_removal(migration) -> None:
    assert migration.Migration.dependencies == [
        ("netbox_proxbox", "0085_remove_vm_reflection_custom_fields"),
    ]


def test_a_field_carrying_an_unrelated_binding_is_unbound_but_not_deleted(migration):
    """Deleting by name alone would destroy data this plugin never wrote.

    This plugin is public. Nothing stops an operator binding one of these names
    to an object type Proxbox never used, or repurposing the field outright. A
    `filter(name__in=...).delete()` takes the definition and every value with
    it, including values for object types this migration has no claim on -- and
    the reverse cannot restore them, because it only knows Proxbox's own
    bindings.

    So a field with a foreign binding must keep its row and that binding, while
    still losing the bindings Proxbox created.
    """
    store, rows = _seed(migration)
    apps = _FakeApps(migration, store, rows)
    content_types = apps.content_type_manager

    canonical = content_types.get(app_label="dcim", model="device")
    foreign = content_types.get(app_label="dcim", model="rack")

    shared = store["proxmox_os"]
    shared.object_types = _FakeM2M([canonical, foreign])

    # A field bound only to what Proxbox created is the ordinary case.
    proxbox_only = store["proxmox_notes"]
    proxbox_only.object_types = _FakeM2M([canonical])

    migration.remove_other_reflection_custom_fields(apps, _FakeSchemaEditor())

    assert "proxmox_os" in store, (
        "a field carrying a binding Proxbox did not create must survive, or the "
        "migration destroys an operator's own data"
    )
    surviving = [
        content_type.model for content_type in store["proxmox_os"].object_types.members
    ]
    assert surviving == ["rack"], (
        "only Proxbox's own bindings may be released; the foreign one stays"
    )

    assert "proxmox_notes" not in store, (
        "a field bound only to what Proxbox created is still deleted outright"
    )


def test_reverse_does_not_overwrite_an_operator_owned_field(migration):
    """A rollback must not rewrite a definition that is not ours.

    A field survives the forward pass precisely when an operator bound it
    somewhere Proxbox never did -- it is theirs, and its type, label,
    description and visibility may be nothing like our definition. Restoring
    with `update_or_create` would overwrite all of that, making the rollback
    destructive in a second, quieter way. It must recreate a missing field in
    full, and leave an existing one alone apart from re-adding the bindings the
    forward pass released.
    """
    store: dict = {}
    apps = _FakeApps(migration, store, {})
    content_types = apps.content_type_manager

    survivor = _FakeCustomField(
        "proxmox_os",
        type="integer",
        label="Operator's own label",
        description="repurposed by the operator",
        ui_visible="hidden",
    )
    store["proxmox_os"] = survivor

    migration.restore_other_reflection_custom_fields(apps, _FakeSchemaEditor())

    assert survivor.label == "Operator's own label", (
        "a rollback must not rewrite the definition of a field the operator owns"
    )
    assert survivor.type == "integer"
    assert survivor.description == "repurposed by the operator"
    assert survivor.ui_visible == "hidden"
    # It still regains the bindings the forward pass took away.
    assert survivor.object_types.added, "released bindings must be restored"

    # A field that really was deleted is recreated in full.
    recreated = store["proxmox_notes"]
    assert recreated.label and recreated.type
    assert recreated.object_types.added
    assert content_types.by_name


def test_a_repurposed_field_on_a_canonical_binding_is_left_entirely_alone(migration):
    """Name plus object type is not proof of ownership.

    An operator can repurpose one of these names on an object type Proxbox also
    used -- same name, same binding, different field. Releasing that binding
    would strip values this plugin never wrote, and the reverse restores
    definitions and bindings but never JSON, so the loss would be permanent.
    A row whose defining metadata has drifted is therefore skipped completely:
    its binding stays, and its values stay.
    """
    store, rows_by_model = _seed(migration)
    repurposed = store["proxmox_os"]
    repurposed.type = "integer"
    repurposed.label = "Operator's own meaning"

    apps = _FakeApps(migration, store, rows_by_model)
    migration.remove_other_reflection_custom_fields(apps, _FakeSchemaEditor())

    assert "proxmox_os" in store, "a repurposed field must not be deleted"
    assert repurposed.object_types.removed == [], (
        "a repurposed field's bindings must not be released"
    )

    device_row = rows_by_model[("dcim", "Device")][0]
    assert device_row.custom_field_data.get("proxmox_os") == "stale-proxmox_os", (
        "values under a repurposed field belong to the operator and must survive"
    )
    # A field that still matches our definition is retired normally.
    assert "proxmox_notes" not in store
    assert "proxmox_notes" not in device_row.custom_field_data


def test_legacy_cf_prefixed_keys_are_stripped_too(migration):
    """The backfill era accepted both spellings, so both are stale now."""
    store, rows_by_model = _seed(migration)
    device_rows = rows_by_model[("dcim", "Device")]
    device_rows[0].custom_field_data["cf_proxmox_os"] = "legacy-alias"
    device_rows[0].custom_field_data["cf_operator_field"] = "not ours"

    apps = _FakeApps(migration, store, rows_by_model)
    migration.remove_other_reflection_custom_fields(apps, _FakeSchemaEditor())

    data = device_rows[0].custom_field_data
    assert "cf_proxmox_os" not in data, (
        "the prefixed alias holds the same retired value and must go with it"
    )
    assert data["cf_operator_field"] == "not ours", (
        "only the released names are stripped, in either spelling"
    )
