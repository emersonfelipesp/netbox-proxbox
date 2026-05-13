"""Tests for hardware_discovery_enabled round-trip in SettingsView."""

from __future__ import annotations

import sys
import types
from types import SimpleNamespace

from tests.conftest import load_plugin_module
from tests.test_settings_view_encryption import (
    _BASE_CLEANED_DATA,
    _fake_form_class,
    _fake_settings_obj,
    _get_request,
    _post_request,
)


def _load_settings_view(monkeypatch, form_class=None):
    stub_form_module = types.ModuleType("netbox_proxbox.forms.settings")

    class _DefaultForm:
        def __init__(self, *args, **kwargs):
            pass

    stub_form_module.ProxboxPluginSettingsForm = form_class or _DefaultForm
    monkeypatch.setitem(sys.modules, "netbox_proxbox.forms.settings", stub_form_module)
    return load_plugin_module("netbox_proxbox.views.settings", monkeypatch=monkeypatch)


def _settings_with_hardware_discovery(
    *, enabled: bool, encryption_key: str = ""
) -> SimpleNamespace:
    obj = _fake_settings_obj(encryption_key=encryption_key)
    obj.hardware_discovery_enabled = enabled
    return obj


def test_get_populates_hardware_discovery_enabled_false(monkeypatch):
    captured_initial: list[dict] = []
    form_cls = _fake_form_class({}, capture_initial=captured_initial)
    module = _load_settings_view(monkeypatch, form_class=form_cls)

    settings_obj = _settings_with_hardware_discovery(enabled=False)
    monkeypatch.setattr(
        module, "ProxboxPluginSettings", SimpleNamespace(get_solo=lambda: settings_obj)
    )
    monkeypatch.setattr(module, "ProxboxPluginSettingsForm", form_cls)

    module.SettingsView().get(_get_request())

    assert captured_initial, "form constructor must have been called"
    assert captured_initial[0]["hardware_discovery_enabled"] is False


def test_get_populates_hardware_discovery_enabled_true(monkeypatch):
    captured_initial: list[dict] = []
    form_cls = _fake_form_class({}, capture_initial=captured_initial)
    module = _load_settings_view(monkeypatch, form_class=form_cls)

    settings_obj = _settings_with_hardware_discovery(enabled=True)
    monkeypatch.setattr(
        module, "ProxboxPluginSettings", SimpleNamespace(get_solo=lambda: settings_obj)
    )
    monkeypatch.setattr(module, "ProxboxPluginSettingsForm", form_cls)

    module.SettingsView().get(_get_request())

    assert captured_initial[0]["hardware_discovery_enabled"] is True


def test_post_sets_hardware_discovery_enabled_from_cleaned_data(monkeypatch):
    cleaned = {**_BASE_CLEANED_DATA, "hardware_discovery_enabled": True}
    module = _load_settings_view(monkeypatch, form_class=_fake_form_class(cleaned))

    settings_obj = _settings_with_hardware_discovery(enabled=False)
    monkeypatch.setattr(
        module, "ProxboxPluginSettings", SimpleNamespace(get_solo=lambda: settings_obj)
    )
    monkeypatch.setattr(module, "ProxboxPluginSettingsForm", _fake_form_class(cleaned))

    module.SettingsView().post(_post_request())

    assert settings_obj.hardware_discovery_enabled is True
    assert settings_obj._saved, "save() must have been called"
    assert "hardware_discovery_enabled" in settings_obj._saved[0].get(
        "update_fields", []
    )


def test_post_defaults_missing_flag_to_false(monkeypatch):
    """A missing hardware_discovery_enabled key in cleaned_data must default to False."""
    cleaned = {**_BASE_CLEANED_DATA}  # no hardware_discovery_enabled key
    module = _load_settings_view(monkeypatch, form_class=_fake_form_class(cleaned))

    settings_obj = _settings_with_hardware_discovery(enabled=True)
    monkeypatch.setattr(
        module, "ProxboxPluginSettings", SimpleNamespace(get_solo=lambda: settings_obj)
    )
    monkeypatch.setattr(module, "ProxboxPluginSettingsForm", _fake_form_class(cleaned))

    module.SettingsView().post(_post_request())

    assert settings_obj.hardware_discovery_enabled is False


def test_post_disables_hardware_discovery_when_unchecked(monkeypatch):
    cleaned = {**_BASE_CLEANED_DATA, "hardware_discovery_enabled": False}
    module = _load_settings_view(monkeypatch, form_class=_fake_form_class(cleaned))

    settings_obj = _settings_with_hardware_discovery(enabled=True)
    monkeypatch.setattr(
        module, "ProxboxPluginSettings", SimpleNamespace(get_solo=lambda: settings_obj)
    )
    monkeypatch.setattr(module, "ProxboxPluginSettingsForm", _fake_form_class(cleaned))

    module.SettingsView().post(_post_request())

    assert settings_obj.hardware_discovery_enabled is False
    update_fields = settings_obj._saved[0].get("update_fields", [])
    assert "hardware_discovery_enabled" in update_fields
