"""Execute migration 0084 rather than reading its source.

The companion contract test pins the migration's constants and asserts on its
source text. That is necessary but not sufficient, and this repository's own
guidance records the reason: a substring assertion is satisfied by both the
correct and the defective form, so a guard built that way can pass while
proving nothing. A migration that deleted by the wrong predicate, stripped the
wrong JSON keys, or restored an incomplete definition set would satisfy every
source check in that file.

These tests call the real data callables with a fake ``apps`` registry
implementing only the ORM surface they actually use. No Django, so they run in
the mocked suite, but the code under test is the code that will run against
production NetBox.
"""

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
    / "0085_remove_vm_reflection_custom_fields.py"
)

# Bound to other object types, or owned by another sub-issue or another plugin.
# Every one of these must survive the migration untouched.
OUT_OF_SCOPE = (
    "proxmox_last_updated",
    "proxbox_last_run_id",
    "proxmox_node",
    "proxmox_cluster",
    "proxmox_link",
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
    "nginx_systemd_unit",
)


def _install_django_migrations_stub() -> None:
    """Provide the ``django.db.migrations`` names the module binds at import.

    Django is not installed in the mocked suite; the repository already
    path-loads migration helpers this way (see
    ``test_hardware_discovery_custom_fields_migration``). Only the attributes
    the module actually references are stubbed, so an import of anything else
    fails loudly instead of silently resolving to a mock.
    """
    if "django" not in sys.modules:
        sys.modules["django"] = types.ModuleType("django")
    if "django.db" not in sys.modules:
        sys.modules["django.db"] = types.ModuleType("django.db")
    if not hasattr(sys.modules["django.db"], "migrations"):
        stub = types.ModuleType("django.db.migrations")

        class _Migration:
            dependencies: list = []
            operations: list = []

        def _run_python(code, reverse_code=None, **_kwargs):
            return ("RunPython", code, reverse_code)

        def _remove_field(**kwargs):
            return ("RemoveField", kwargs)

        stub.Migration = _Migration
        stub.RunPython = _run_python
        stub.RemoveField = _remove_field
        sys.modules["django.db.migrations"] = stub
        sys.modules["django.db"].migrations = stub


def _load_migration():
    _install_django_migrations_stub()
    spec = importlib.util.spec_from_file_location("migration_0084", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeCustomField:
    def __init__(self, name: str, **fields: Any) -> None:
        self.name = name
        self.__dict__.update(fields)
        self.object_types = _FakeM2M()


class _FakeM2M:
    def __init__(self) -> None:
        self.added: list[Any] = []

    def add(self, value: Any) -> None:
        self.added.append(value)


class _FakeVM:
    def __init__(self, pk: int, custom_field_data: Any) -> None:
        self.pk = pk
        self.custom_field_data = custom_field_data


class _CustomFieldQuerySet:
    def __init__(self, store: dict[str, _FakeCustomField], names: list[str]) -> None:
        self._store = store
        self._names = names

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
        # The migration must select by exact name membership. Any other
        # predicate reaches this fake and fails loudly rather than silently
        # deleting a different set.
        assert set(kwargs) == {"name__in"}, f"unexpected delete predicate: {kwargs}"
        wanted = [n for n in kwargs["name__in"] if n in self._store]
        return _CustomFieldQuerySet(self._store, wanted)

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


class _VMManager:
    def __init__(self, rows: list[_FakeVM]) -> None:
        self.rows = rows
        self.bulk_updated: list[int] = []

    def using(self, _alias: str) -> "_VMManager":
        return self

    def only(self, *_fields: str) -> "_VMManager":
        return self

    def iterator(self, chunk_size: int | None = None) -> Any:
        return iter(list(self.rows))

    def bulk_update(self, objs: Any, fields: Any, batch_size: int | None = None) -> int:
        materialized = list(objs)
        assert tuple(fields) == ("custom_field_data",)
        self.bulk_updated.extend(vm.pk for vm in materialized)
        return len(materialized)


class _ContentTypeManager:
    def __init__(self, present: bool = True) -> None:
        self.present = present
        self.sentinel = object()

    def using(self, _alias: str) -> "_ContentTypeManager":
        return self

    def get(self, **kwargs: Any) -> Any:
        assert kwargs == {"app_label": "virtualization", "model": "virtualmachine"}
        if not self.present:
            raise _ContentTypeDoesNotExist()
        return self.sentinel


class _ContentTypeDoesNotExist(Exception):
    pass


class _FakeApps:
    def __init__(
        self,
        custom_fields: dict[str, _FakeCustomField],
        vms: list[_FakeVM],
        *,
        content_type_present: bool = True,
    ) -> None:
        self.custom_field_store = custom_fields
        self.custom_field_model = type(
            "CustomField", (), {"objects": _CustomFieldManager(custom_fields)}
        )
        self.vm_manager = _VMManager(vms)
        self.vm_model = type("VirtualMachine", (), {"objects": self.vm_manager})
        self.content_type_manager = _ContentTypeManager(content_type_present)
        self.content_type_model = type(
            "ContentType",
            (),
            {
                "objects": self.content_type_manager,
                "DoesNotExist": _ContentTypeDoesNotExist,
            },
        )

    def get_model(self, app_label: str, model_name: str) -> Any:
        key = (app_label, model_name)
        if key == ("extras", "CustomField"):
            return self.custom_field_model
        if key == ("virtualization", "VirtualMachine"):
            return self.vm_model
        if key == ("contenttypes", "ContentType"):
            return self.content_type_model
        raise AssertionError(f"migration touched an unexpected model: {key}")


class _FakeSchemaEditor:
    class connection:  # noqa: N801 - mirrors the Django attribute path
        alias = "default"


@pytest.fixture
def migration():
    return _load_migration()


def _seed(migration_module) -> tuple[dict[str, _FakeCustomField], list[_FakeVM]]:
    names = list(migration_module.VM_REFLECTION_CUSTOM_FIELD_NAMES)
    store = {name: _FakeCustomField(name) for name in names + list(OUT_OF_SCOPE)}
    vms = [
        _FakeVM(
            1,
            {
                **{name: 7 for name in names},
                "source_packer_template": 42,
                "proxbox_intent_state": "applied",
                "an_unrelated_operator_field": "keep me",
            },
        ),
        _FakeVM(2, {"an_unrelated_operator_field": "untouched"}),
        _FakeVM(3, None),
    ]
    return store, vms


def test_forward_deletes_exactly_the_twelve_and_spares_everything_else(migration):
    store, vms = _seed(migration)
    apps = _FakeApps(store, vms)

    migration.remove_vm_reflection_custom_fields(apps, _FakeSchemaEditor())

    for name in migration.VM_REFLECTION_CUSTOM_FIELD_NAMES:
        assert name not in store, f"{name} should have been deleted"
    for name in OUT_OF_SCOPE:
        assert name in store, (
            f"{name} is owned by another sub-issue or plugin and must survive; "
            "deleting it would be an over-broad migration"
        )


def test_forward_strips_only_the_named_keys_and_keeps_the_rest(migration):
    store, vms = _seed(migration)
    apps = _FakeApps(store, vms)

    migration.remove_vm_reflection_custom_fields(apps, _FakeSchemaEditor())

    first = vms[0].custom_field_data
    for name in migration.VM_REFLECTION_CUSTOM_FIELD_NAMES:
        assert name not in first
    # Keys owned by other sub-issues and by other plugins stay in the JSON;
    # their definitions still exist, so removing their values would be data loss.
    assert first["source_packer_template"] == 42
    assert first["proxbox_intent_state"] == "applied"
    assert first["an_unrelated_operator_field"] == "keep me"

    # A row with nothing to strip is not rewritten, and a null payload does not
    # raise -- both are real states on an installation that never used the CFs.
    assert vms[1].custom_field_data == {"an_unrelated_operator_field": "untouched"}
    assert vms[2].custom_field_data is None
    assert apps.vm_manager.bulk_updated == [1]


def test_forward_is_idempotent(migration):
    store, vms = _seed(migration)
    apps = _FakeApps(store, vms)

    migration.remove_vm_reflection_custom_fields(apps, _FakeSchemaEditor())
    survivors = dict(store)
    first_payload = dict(vms[0].custom_field_data)

    # A second application -- a re-run, or a fresh install where the fields were
    # never registered -- must be a no-op rather than an error.
    migration.remove_vm_reflection_custom_fields(apps, _FakeSchemaEditor())
    assert store == survivors
    assert vms[0].custom_field_data == first_payload


def test_reverse_restores_every_definition_and_binds_the_vm_content_type(migration):
    store: dict[str, _FakeCustomField] = {}
    apps = _FakeApps(store, [])

    migration.restore_vm_reflection_custom_fields(apps, _FakeSchemaEditor())

    restored = set(store)
    assert restored == set(migration.VM_REFLECTION_CUSTOM_FIELD_NAMES), (
        "the reverse must recreate every field the forward removed, or a "
        "rollback silently drops part of the schema"
    )
    sentinel = apps.content_type_manager.sentinel
    for name, field in store.items():
        assert field.object_types.added == [sentinel], (
            f"{name} was recreated without its VirtualMachine binding, which "
            "leaves a definition that renders nowhere"
        )
        assert getattr(field, "type", None), f"{name} restored without a type"
        assert getattr(field, "label", None), f"{name} restored without a label"


def test_reverse_is_a_noop_without_the_virtualmachine_content_type(migration):
    """A rollback on an installation without virtualization must not raise."""
    store: dict[str, _FakeCustomField] = {}
    apps = _FakeApps(store, [], content_type_present=False)

    migration.restore_vm_reflection_custom_fields(apps, _FakeSchemaEditor())
    assert store == {}
