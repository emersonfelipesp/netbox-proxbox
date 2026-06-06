"""Tests for interface_batch_size / interface_batch_delay_ms round-trip in SettingsView.

Regression coverage for the bug where the settings view never read or wrote
``interface_batch_size`` / ``interface_batch_delay_ms``, so values entered in the
settings UI were silently dropped and never persisted to ``ProxboxPluginSettings``.
"""

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


def _settings_with_interface_batch(
    *, size: int, delay_ms: int, encryption_key: str = ""
) -> SimpleNamespace:
    obj = _fake_settings_obj(encryption_key=encryption_key)
    obj.interface_batch_size = size
    obj.interface_batch_delay_ms = delay_ms
    return obj


def test_get_populates_interface_batch_fields(monkeypatch):
    captured_initial: list[dict] = []
    form_cls = _fake_form_class({}, capture_initial=captured_initial)
    module = _load_settings_view(monkeypatch, form_class=form_cls)

    settings_obj = _settings_with_interface_batch(size=12, delay_ms=250)
    monkeypatch.setattr(
        module, "ProxboxPluginSettings", SimpleNamespace(get_solo=lambda: settings_obj)
    )
    monkeypatch.setattr(module, "ProxboxPluginSettingsForm", form_cls)

    module.SettingsView().get(_get_request())

    assert captured_initial, "form constructor must have been called"
    assert captured_initial[0]["interface_batch_size"] == 12
    assert captured_initial[0]["interface_batch_delay_ms"] == 250


def test_post_persists_interface_batch_fields_from_cleaned_data(monkeypatch):
    cleaned = {
        **_BASE_CLEANED_DATA,
        "interface_batch_size": 25,
        "interface_batch_delay_ms": 750,
    }
    module = _load_settings_view(monkeypatch, form_class=_fake_form_class(cleaned))

    settings_obj = _settings_with_interface_batch(size=5, delay_ms=100)
    monkeypatch.setattr(
        module, "ProxboxPluginSettings", SimpleNamespace(get_solo=lambda: settings_obj)
    )
    monkeypatch.setattr(module, "ProxboxPluginSettingsForm", _fake_form_class(cleaned))

    module.SettingsView().post(_post_request())

    assert settings_obj.interface_batch_size == 25
    assert settings_obj.interface_batch_delay_ms == 750
    assert settings_obj._saved, "save() must have been called"
    update_fields = settings_obj._saved[0].get("update_fields", [])
    assert "interface_batch_size" in update_fields
    assert "interface_batch_delay_ms" in update_fields
