"""Behavior tests for the hardware-discovery CustomField registration callables.

These callables originally shipped in ``0049_register_hardware_discovery_cfs``;
they now live in the consolidated ``_v0_0_15_release_data`` helper module
(imported by ``0037_v0_0_15_release``). The contract is unchanged: register
six custom fields on ``dcim.Device`` and ``dcim.Interface`` so proxbox-api's
hardware-discovery pass has somewhere to write parsed dmidecode + ethtool
output. This test invokes ``register_hardware_discovery_cfs`` against a fake
``apps`` registry and verifies the six fields are created with the right
types, content types, and UI flags, and that the operation is idempotent
(re-running creates no duplicates).
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_MODULE_PATH = (
    REPO_ROOT
    / "netbox_proxbox"
    / "migrations"
    / "_v0_0_15_release_data.py"
)
CONSOLIDATED_MIGRATION_PATH = (
    REPO_ROOT
    / "netbox_proxbox"
    / "migrations"
    / "0037_v0_0_15_release.py"
)


@pytest.fixture
def migration_module():
    # Stub ``django.db.models`` so ``from django.db.models import Max`` succeeds
    # without a real Django installation.
    if "django" not in sys.modules:
        sys.modules["django"] = types.ModuleType("django")
    if "django.db" not in sys.modules:
        sys.modules["django.db"] = types.ModuleType("django.db")
    if "django.db.models" not in sys.modules:
        models_stub = types.ModuleType("django.db.models")
        models_stub.Max = lambda *a, **kw: None
        sys.modules["django.db.models"] = models_stub
        sys.modules["django.db"].models = models_stub

    spec = importlib.util.spec_from_file_location(
        "_v0_0_15_release_data_under_test", DATA_MODULE_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeContentType:
    _by_key: dict = {}
    _pk_counter = 0

    def __init__(self, app_label: str, model: str):
        self.app_label = app_label
        self.model = model
        type(self)._pk_counter += 1
        self.pk = type(self)._pk_counter

    class _Manager:
        def get_or_create(self, *, app_label: str, model: str):
            key = (app_label, model)
            if key in _FakeContentType._by_key:
                return _FakeContentType._by_key[key], False
            ct = _FakeContentType(app_label, model)
            _FakeContentType._by_key[key] = ct
            return ct, True

    objects = _Manager()


class _FakeObjectTypes:
    def __init__(self):
        self._items: list = []

    def add(self, ct):
        self._items.append(ct)

    def filter(self, **kwargs):
        pk = kwargs["pk"]
        matching = [c for c in self._items if c.pk == pk]
        return SimpleNamespace(exists=lambda: bool(matching))


class _FakeCustomField:
    _by_name: dict = {}

    def __init__(self, *, name, type=None, label=None, description=None, **kwargs):
        self.name = name
        self.type = type
        self.label = label
        self.description = description
        self.ui_visible = kwargs.get("ui_visible")
        self.ui_editable = kwargs.get("ui_editable")
        self.filter_logic = kwargs.get("filter_logic")
        self.required = kwargs.get("required", False)
        self.search_weight = kwargs.get("search_weight", 0)
        self.object_types = _FakeObjectTypes()

    class _Manager:
        def get_or_create(self, *, name: str, defaults: dict):
            if name in _FakeCustomField._by_name:
                return _FakeCustomField._by_name[name], False
            cf = _FakeCustomField(name=name, **defaults)
            _FakeCustomField._by_name[name] = cf
            return cf, True

        def filter(self, **kwargs):
            names = kwargs.get("name__in", [])
            matched = [
                _FakeCustomField._by_name[n]
                for n in names
                if n in _FakeCustomField._by_name
            ]

            def _delete():
                for n in names:
                    _FakeCustomField._by_name.pop(n, None)

            return SimpleNamespace(delete=_delete, items=matched)

    objects = _Manager()


def _fresh_state():
    _FakeContentType._by_key = {}
    _FakeContentType._pk_counter = 0
    _FakeCustomField._by_name = {}


def _fake_apps():
    return SimpleNamespace(
        get_model=lambda app, model: {
            ("extras", "CustomField"): _FakeCustomField,
            ("contenttypes", "ContentType"): _FakeContentType,
        }[(app, model)]
    )


_EXPECTED_DEVICE_FIELDS = {
    "hardware_chassis_serial": "text",
    "hardware_chassis_manufacturer": "text",
    "hardware_chassis_product": "text",
}
_EXPECTED_INTERFACE_FIELDS = {
    "nic_speed_gbps": "integer",
    "nic_duplex": "text",
    "nic_link": "boolean",
}


def test_migration_creates_all_six_fields(migration_module):
    _fresh_state()
    migration_module.register_hardware_discovery_cfs(_fake_apps(), None)

    created = set(_FakeCustomField._by_name)
    assert (set(_EXPECTED_DEVICE_FIELDS) | set(_EXPECTED_INTERFACE_FIELDS)).issubset(
        created
    ), f"missing fields: created={created}"


def test_device_fields_bind_to_dcim_device(migration_module):
    _fresh_state()
    migration_module.register_hardware_discovery_cfs(_fake_apps(), None)
    for name in _EXPECTED_DEVICE_FIELDS:
        cf = _FakeCustomField._by_name[name]
        cts = [(c.app_label, c.model) for c in cf.object_types._items]
        assert ("dcim", "device") in cts, (
            f"{name} not bound to dcim.device — bound to {cts}"
        )


def test_interface_fields_bind_to_dcim_interface(migration_module):
    _fresh_state()
    migration_module.register_hardware_discovery_cfs(_fake_apps(), None)
    for name in _EXPECTED_INTERFACE_FIELDS:
        cf = _FakeCustomField._by_name[name]
        cts = [(c.app_label, c.model) for c in cf.object_types._items]
        assert ("dcim", "interface") in cts, (
            f"{name} not bound to dcim.interface — bound to {cts}"
        )


def test_field_types_are_correct(migration_module):
    _fresh_state()
    migration_module.register_hardware_discovery_cfs(_fake_apps(), None)
    for name, type_ in {
        **_EXPECTED_DEVICE_FIELDS,
        **_EXPECTED_INTERFACE_FIELDS,
    }.items():
        cf = _FakeCustomField._by_name[name]
        assert cf.type == type_, f"{name} expected type {type_}, got {cf.type}"


def test_fields_are_read_only_in_ui(migration_module):
    """Hardware discovery writes these — operators should not edit them by hand."""
    _fresh_state()
    migration_module.register_hardware_discovery_cfs(_fake_apps(), None)
    for name in (*_EXPECTED_DEVICE_FIELDS, *_EXPECTED_INTERFACE_FIELDS):
        cf = _FakeCustomField._by_name[name]
        assert cf.ui_visible == "always", f"{name} ui_visible={cf.ui_visible!r}"
        assert cf.ui_editable == "hidden", f"{name} ui_editable={cf.ui_editable!r}"
        assert cf.filter_logic == "disabled"
        assert cf.required is False


def test_migration_is_idempotent(migration_module):
    """Running register twice must produce a single row per name with one CT each."""
    _fresh_state()
    migration_module.register_hardware_discovery_cfs(_fake_apps(), None)
    snapshot = {n: cf for n, cf in _FakeCustomField._by_name.items()}

    migration_module.register_hardware_discovery_cfs(_fake_apps(), None)

    assert set(_FakeCustomField._by_name) == set(snapshot), (
        "second run created or removed CustomField rows"
    )
    for name, cf in _FakeCustomField._by_name.items():
        assert cf is snapshot[name], f"{name} replaced on second run"
        # Each CF must still have exactly one bound ContentType.
        assert len(cf.object_types._items) == 1, (
            f"{name} accumulated duplicate ContentTypes: {cf.object_types._items}"
        )


def test_unregister_removes_all_six_fields(migration_module):
    _fresh_state()
    migration_module.register_hardware_discovery_cfs(_fake_apps(), None)
    assert len(_FakeCustomField._by_name) == 6

    migration_module.unregister_hardware_discovery_cfs(_fake_apps(), None)
    assert _FakeCustomField._by_name == {}


def test_consolidated_migration_pins_required_dependencies():
    """The consolidated migration anchors at 0036 and pulls in extras/dcim/contenttypes."""
    source = CONSOLIDATED_MIGRATION_PATH.read_text(encoding="utf-8")
    assert "('netbox_proxbox', '0036_add_overwrite_vm_type')" in source
    assert "'extras'" in source
    assert "'dcim'" in source
    assert "'contenttypes'" in source
    assert "register_hardware_discovery_cfs" in source
    assert "unregister_hardware_discovery_cfs" in source
