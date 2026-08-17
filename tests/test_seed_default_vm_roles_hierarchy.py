"""Regression coverage for the VM-role seed migration across NetBox hierarchy backends.

NetBox 4.7 migrated nested group models (``dcim.DeviceRole`` among them) from
django-mptt to PostgreSQL ltree, dropping ``tree_id``/``lft``/``rght``/``level``.
``seed_default_vm_roles`` used to aggregate ``Max("tree_id")`` and pass all four
as creation defaults unconditionally, so on 4.7 the very first plugin migration
raised ``FieldError: Cannot resolve keyword 'tree_id' into field`` — a fresh
install could not run ``manage.py migrate`` at all.

These tests drive the migration callable with fake historical models whose field
sets mimic each NetBox generation, which is what a data migration actually sees:
inside a migration the model is rebuilt from migration state, so its concrete
fields are the only trustworthy signal for which backend is in play.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from typing import Any

import pytest


class _StubMax:
    """Stand-in for ``django.db.models.Max`` — records the column it wraps."""

    def __init__(self, field_name: str) -> None:
        self.field_name = field_name

    def __str__(self) -> str:
        return f"Max({self.field_name})"


def _install_minimal_django_models() -> None:
    """Provide just ``django.db.models.Max`` for the mocked suite.

    The migration data module imports it at module scope; the mocked suite has
    no real Django. Only installed when absent, so the NetBox-backed suite keeps
    the genuine article.
    """
    if "django.db.models" in sys.modules:
        return
    django_mod = sys.modules.setdefault("django", types.ModuleType("django"))
    if not hasattr(django_mod, "__path__"):
        django_mod.__path__ = []  # type: ignore[attr-defined]
    db_mod = sys.modules.setdefault("django.db", types.ModuleType("django.db"))
    if not hasattr(db_mod, "__path__"):
        db_mod.__path__ = []  # type: ignore[attr-defined]
    models_mod = types.ModuleType("django.db.models")
    models_mod.Max = _StubMax  # type: ignore[attr-defined]
    sys.modules["django.db.models"] = models_mod


def _load_migration_data_module() -> Any:
    """Load the leading-underscore data module without importing the package."""
    _install_minimal_django_models()
    module_path = (
        Path(__file__).resolve().parents[1]
        / "netbox_proxbox"
        / "migrations"
        / "_v0_0_15_release_data.py"
    )
    spec = importlib.util.spec_from_file_location(
        "v0_0_15_release_data_under_test", module_path
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


migration_data = _load_migration_data_module()

# Transcribed from the two NetBox generations, not derived from the code under
# test. 4.5/4.6 DeviceRole is django-mptt backed; 4.7 is ltree backed and the
# `path` column is trigger-maintained ("do not write to it from Python").
MPTT_DEVICE_ROLE_FIELDS = (
    "id",
    "name",
    "slug",
    "color",
    "vm_role",
    "parent",
    "level",
    "lft",
    "rght",
    "tree_id",
)
LTREE_DEVICE_ROLE_FIELDS = (
    "id",
    "name",
    "slug",
    "color",
    "vm_role",
    "parent",
    "path",
    "sort_path",
)


class _FakeField:
    def __init__(self, name: str) -> None:
        self.name = name


class _FakeMeta:
    def __init__(self, field_names: tuple[str, ...]) -> None:
        self._fields = [_FakeField(name) for name in field_names]

    def get_fields(self) -> list[_FakeField]:
        return list(self._fields)


class _FakeRole:
    def __init__(self, **kwargs: Any) -> None:
        self.__dict__.update(kwargs)


class _FakeManager:
    """Minimal stand-in for the historical model manager used by the migration."""

    def __init__(self, field_names: tuple[str, ...]) -> None:
        self.field_names = field_names
        self.created_defaults: list[dict[str, Any]] = []
        self.aggregate_calls: list[tuple[str, ...]] = []

    def aggregate(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        # Record the aggregate so a test can prove it is not attempted at all on
        # a backend that lacks the column — the original crash was here.
        expressions = [getattr(arg, "source_expressions", arg) for arg in args]
        self.aggregate_calls.append(tuple(str(expr) for expr in expressions))
        if "tree_id" not in self.field_names:
            raise AssertionError(
                "aggregated over an MPTT column on a non-MPTT DeviceRole"
            )
        return {"tree_id__max": 7}

    def get_or_create(self, slug: str, defaults: dict[str, Any]):
        unknown = set(defaults) - set(self.field_names)
        if unknown:
            # Mirrors Django rejecting unknown kwargs for the historical model.
            raise TypeError(f"invalid field(s) for DeviceRole: {sorted(unknown)}")
        self.created_defaults.append(dict(defaults))
        return _FakeRole(slug=slug, **defaults), True

    def filter(self, **kwargs: Any) -> "_FakeManager":
        return self

    def first(self) -> None:
        return None


class _FakeModel:
    def __init__(self, field_names: tuple[str, ...]) -> None:
        self._meta = _FakeMeta(field_names)
        self.objects = _FakeManager(field_names)


class _FakeApps:
    def __init__(self, device_role_fields: tuple[str, ...]) -> None:
        self.device_role = _FakeModel(device_role_fields)
        # ProxboxPluginSettings: the migration bails out when no singleton row
        # exists, which is the path these tests exercise.
        self.settings_model = _FakeModel(("id", "singleton_key"))

    def get_model(self, app_label: str, model_name: str) -> _FakeModel:
        if (app_label, model_name) == ("dcim", "DeviceRole"):
            return self.device_role
        if (app_label, model_name) == ("netbox_proxbox", "ProxboxPluginSettings"):
            return self.settings_model
        raise AssertionError(f"unexpected model {app_label}.{model_name}")


def test_detects_mptt_backend_on_netbox_4_5_and_4_6() -> None:
    model = _FakeModel(MPTT_DEVICE_ROLE_FIELDS)
    assert migration_data._model_has_mptt_columns(model) is True


def test_detects_ltree_backend_on_netbox_4_7() -> None:
    model = _FakeModel(LTREE_DEVICE_ROLE_FIELDS)
    assert migration_data._model_has_mptt_columns(model) is False


def test_seed_supplies_mptt_bookkeeping_on_the_mptt_backend() -> None:
    """Backward compatibility: 4.5/4.6 behaviour must be byte-for-byte unchanged."""
    apps = _FakeApps(MPTT_DEVICE_ROLE_FIELDS)

    migration_data.seed_default_vm_roles(apps, schema_editor=None)

    created = apps.device_role.objects.created_defaults
    assert len(created) == len(migration_data.VM_ROLE_SEEDS)
    # Max("tree_id") returned 7, so the first new tree is 8 and the second 9.
    assert [defaults["tree_id"] for defaults in created] == [8, 9]
    for defaults in created:
        assert defaults["level"] == 0
        assert defaults["lft"] == 1
        assert defaults["rght"] == 2
        assert defaults["vm_role"] is True


def test_seed_omits_mptt_bookkeeping_on_the_ltree_backend() -> None:
    """The actual 4.7 regression: this raised FieldError before the fix."""
    apps = _FakeApps(LTREE_DEVICE_ROLE_FIELDS)

    migration_data.seed_default_vm_roles(apps, schema_editor=None)

    created = apps.device_role.objects.created_defaults
    assert len(created) == len(migration_data.VM_ROLE_SEEDS)
    for defaults in created:
        assert not (set(defaults) & migration_data._MPTT_BOOKKEEPING_FIELDS), (
            "MPTT bookkeeping must not be written on an ltree-backed DeviceRole"
        )
        # path/sort_path are trigger-maintained; the migration must not set them.
        assert "path" not in defaults
        assert "sort_path" not in defaults
        assert defaults["vm_role"] is True


def test_seed_never_aggregates_a_missing_column_on_the_ltree_backend() -> None:
    """The original failure was the aggregate itself, before any create ran."""
    apps = _FakeApps(LTREE_DEVICE_ROLE_FIELDS)

    migration_data.seed_default_vm_roles(apps, schema_editor=None)

    assert apps.device_role.objects.aggregate_calls == []


def test_seed_creates_the_expected_roles_on_both_backends() -> None:
    expected_slugs = [seed["slug"] for seed in migration_data.VM_ROLE_SEEDS]
    assert expected_slugs == ["virtual-machine-qemu", "container-lxc"]

    for field_names in (MPTT_DEVICE_ROLE_FIELDS, LTREE_DEVICE_ROLE_FIELDS):
        apps = _FakeApps(field_names)
        migration_data.seed_default_vm_roles(apps, schema_editor=None)
        names = [d["name"] for d in apps.device_role.objects.created_defaults]
        assert names == ["Virtual Machine (QEMU)", "Container (LXC)"]


@pytest.mark.parametrize(
    "missing_field", sorted(migration_data._MPTT_BOOKKEEPING_FIELDS)
)
def test_a_partial_mptt_field_set_is_treated_as_non_mptt(missing_field: str) -> None:
    """Half-migrated state must not produce a create that references a gone column."""
    field_names = tuple(
        name for name in MPTT_DEVICE_ROLE_FIELDS if name != missing_field
    )
    model = _FakeModel(field_names)
    assert migration_data._model_has_mptt_columns(model) is False
