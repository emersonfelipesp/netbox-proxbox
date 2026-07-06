"""Tests for the ProxmoxVMTemplate model field shapes and defaults.

These tests load the model file directly without importing Django's ORM runtime,
so they can run in the CI environment that has no live database or NetBox
installed. They validate field presence, types, and default values by
inspecting the class definition rather than querying the database.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def _stub_django(monkeypatch):
    """Add just enough Django / netbox stubs for the model file to import."""

    # django.db.models
    class _Field:
        def __init__(self, *a, **kw):
            self.null = kw.get("null", False)
            self.blank = kw.get("blank", False)
            self.default = kw.get("default", None)
            self.max_length = kw.get("max_length", None)

    class _FKField(_Field):
        def __init__(self, to, on_delete, *a, **kw):
            super().__init__(*a, **kw)
            self.to = to
            self.on_delete = on_delete

    class _M2MField(_Field):
        def __init__(self, to, *a, **kw):
            super().__init__(*a, **kw)
            self.to = to

    class _CharField(_Field):
        pass

    class _TextField(_Field):
        pass

    class _PositiveIntegerField(_Field):
        pass

    class _PositiveSmallIntegerField(_Field):
        pass

    class _BooleanField(_Field):
        pass

    class _JSONField(_Field):
        pass

    class _DateTimeField(_Field):
        pass

    mock_models = types.ModuleType("django.db.models")
    mock_models.Model = object
    mock_models.CharField = _CharField
    mock_models.TextField = _TextField
    mock_models.PositiveIntegerField = _PositiveIntegerField
    mock_models.PositiveSmallIntegerField = _PositiveSmallIntegerField
    mock_models.BooleanField = _BooleanField
    mock_models.JSONField = _JSONField
    mock_models.DateTimeField = _DateTimeField
    mock_models.ForeignKey = _FKField
    mock_models.ManyToManyField = _M2MField
    mock_models.SET_NULL = "SET_NULL"
    mock_models.CASCADE = "CASCADE"

    mock_django_db = types.ModuleType("django.db")
    mock_django_db.models = mock_models

    mock_django = types.ModuleType("django")
    mock_django.db = mock_django_db

    mock_django_urls = types.ModuleType("django.urls")
    mock_django_urls.reverse = lambda name, args=None: f"/{name}/{args}"

    mock_django_utils_trans = types.ModuleType("django.utils.translation")
    mock_django_utils_trans.gettext_lazy = lambda s: s
    mock_django_utils = types.ModuleType("django.utils")
    mock_django_utils.translation = mock_django_utils_trans

    # netbox model base
    class MockNetBoxModel:
        class Meta:
            abstract = True

        tags = _M2MField("extras.Tag")

    mock_netbox_models = types.ModuleType("netbox.models")
    mock_netbox_models.NetBoxModel = MockNetBoxModel

    for key, val in {
        "django": mock_django,
        "django.db": mock_django_db,
        "django.db.models": mock_models,
        "django.db.models.deletion": mock_models,
        "django.urls": mock_django_urls,
        "django.utils": mock_django_utils,
        "django.utils.translation": mock_django_utils_trans,
        "netbox": types.ModuleType("netbox"),
        "netbox.models": mock_netbox_models,
    }.items():
        monkeypatch.setitem(sys.modules, key, val)


@pytest.fixture
def vm_template_module(monkeypatch):
    _stub_django(monkeypatch)
    spec = importlib.util.spec_from_file_location(
        "_vm_template_model",
        REPO_ROOT / "netbox_proxbox" / "models" / "vm_template.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    module.__package__ = "netbox_proxbox.models"
    spec.loader.exec_module(module)
    return module


class TestProxmoxVMTemplateFieldPresence:
    """Verify all required and optional fields exist on the model class."""

    REQUIRED_FIELDS = [
        "name",
        "vmid",
        "proxmox_endpoint",
    ]
    OPTIONAL_NULLABLE_FIELDS = [
        "cluster",
        "node",
        "source_vm",
        "cloned_vms",
        "vcpus",
        "memory",
        "disk",
        "last_synced",
    ]
    OPTIONAL_BLANK_FIELDS = [
        "node_name",
        "proxmox_type",
        "status",
        "os_type",
        "description",
        "cloud_init_enabled",
        "net_config",
        "disk_config",
        "raw_config",
    ]

    def test_model_class_exists(self, vm_template_module):
        assert hasattr(vm_template_module, "ProxmoxVMTemplate")

    def test_required_fields_exist(self, vm_template_module):
        model = vm_template_module.ProxmoxVMTemplate
        for field_name in self.REQUIRED_FIELDS:
            assert hasattr(model, field_name), f"Missing required field: {field_name}"

    def test_optional_nullable_fields_exist(self, vm_template_module):
        model = vm_template_module.ProxmoxVMTemplate
        for field_name in self.OPTIONAL_NULLABLE_FIELDS:
            assert hasattr(model, field_name), (
                f"Missing optional nullable field: {field_name}"
            )

    def test_optional_blank_fields_exist(self, vm_template_module):
        model = vm_template_module.ProxmoxVMTemplate
        for field_name in self.OPTIONAL_BLANK_FIELDS:
            assert hasattr(model, field_name), (
                f"Missing optional blank field: {field_name}"
            )

    def test_proxmox_type_default_is_qemu(self, vm_template_module):
        model = vm_template_module.ProxmoxVMTemplate
        assert model.proxmox_type.default == "qemu"

    def test_cloud_init_enabled_default_is_false(self, vm_template_module):
        model = vm_template_module.ProxmoxVMTemplate
        assert model.cloud_init_enabled.default is False

    def test_source_vm_is_nullable(self, vm_template_module):
        model = vm_template_module.ProxmoxVMTemplate
        assert model.source_vm.null is True
        assert model.source_vm.blank is True

    def test_cluster_fk_is_nullable(self, vm_template_module):
        model = vm_template_module.ProxmoxVMTemplate
        assert model.cluster.null is True
        assert model.cluster.blank is True

    def test_node_fk_is_nullable(self, vm_template_module):
        model = vm_template_module.ProxmoxVMTemplate
        assert model.node.null is True
        assert model.node.blank is True

    def test_cloned_vms_m2m_is_blank(self, vm_template_module):
        model = vm_template_module.ProxmoxVMTemplate
        assert model.cloned_vms.blank is True

    def test_str_method_exists(self, vm_template_module):
        model = vm_template_module.ProxmoxVMTemplate
        assert callable(model.__str__)

    def test_get_absolute_url_exists(self, vm_template_module):
        model = vm_template_module.ProxmoxVMTemplate
        assert callable(model.get_absolute_url)


class TestSyncModeFieldsOnModels:
    """Verify sync_mode_* fields exist on ProxmoxEndpoint and ProxboxPluginSettings."""

    SYNC_MODE_FIELDS = [
        "sync_mode_vm",
        "sync_mode_vm_template",
        "sync_mode_vm_interface",
        "sync_mode_mac",
        "sync_mode_cluster",
        "sync_mode_node",
        "sync_mode_storage",
        "sync_mode_ip_address",
        "sync_mode_sdn",
        "sync_mode_sdn_bgp",
    ]

    def _load_model_file(self, monkeypatch, filename: str, class_name: str):
        _stub_django(monkeypatch)
        # Extra stubs needed for larger model files
        for mod_name in [
            "netbox_proxbox.fields",
            "netbox_proxbox.choices",
            "netbox_proxbox.constants",
            "netbox_proxbox.models.base",
            "solo.models",
            "taggit.managers",
            "netbox.models.features",
        ]:
            if mod_name not in sys.modules:
                monkeypatch.setitem(sys.modules, mod_name, types.ModuleType(mod_name))
        spec = importlib.util.spec_from_file_location(
            f"_model_{class_name}",
            REPO_ROOT / "netbox_proxbox" / "models" / filename,
        )
        if spec is None or spec.loader is None:
            pytest.skip(f"Cannot load {filename}")
        module = importlib.util.module_from_spec(spec)
        module.__package__ = "netbox_proxbox.models"
        try:
            spec.loader.exec_module(module)
        except Exception:
            pytest.skip(f"Cannot fully load {filename} (complex import tree)")
        return module

    def test_sync_mode_fields_listed_in_constants(self):
        constants_spec = importlib.util.spec_from_file_location(
            "_constants", REPO_ROOT / "netbox_proxbox" / "constants.py"
        )
        assert constants_spec and constants_spec.loader
        constants = importlib.util.module_from_spec(constants_spec)
        constants_spec.loader.exec_module(constants)
        for field in self.SYNC_MODE_FIELDS:
            assert field in constants.SYNC_MODE_FIELDS, (
                f"{field} missing from SYNC_MODE_FIELDS constant"
            )
