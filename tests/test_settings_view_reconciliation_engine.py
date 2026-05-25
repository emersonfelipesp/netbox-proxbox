"""Tests for reconciliation_engine round-trip in SettingsView."""

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


def _settings_with_reconciliation_engine(engine: str) -> SimpleNamespace:
    obj = _fake_settings_obj()
    obj.reconciliation_engine = engine
    return obj


def test_get_populates_reconciliation_engine(monkeypatch):
    captured_initial: list[dict] = []
    form_cls = _fake_form_class({}, capture_initial=captured_initial)
    module = _load_settings_view(monkeypatch, form_class=form_cls)

    settings_obj = _settings_with_reconciliation_engine("compare")
    monkeypatch.setattr(
        module, "ProxboxPluginSettings", SimpleNamespace(get_solo=lambda: settings_obj)
    )
    monkeypatch.setattr(module, "ProxboxPluginSettingsForm", form_cls)

    module.SettingsView().get(_get_request())

    assert captured_initial[0]["reconciliation_engine"] == "compare"


def test_post_sets_reconciliation_engine_from_cleaned_data(monkeypatch):
    cleaned = {**_BASE_CLEANED_DATA, "reconciliation_engine": "rust"}
    module = _load_settings_view(monkeypatch, form_class=_fake_form_class(cleaned))

    settings_obj = _settings_with_reconciliation_engine("python")
    monkeypatch.setattr(
        module, "ProxboxPluginSettings", SimpleNamespace(get_solo=lambda: settings_obj)
    )
    monkeypatch.setattr(module, "ProxboxPluginSettingsForm", _fake_form_class(cleaned))

    module.SettingsView().post(_post_request())

    assert settings_obj.reconciliation_engine == "rust"
    assert settings_obj._saved, "save() must have been called"
    assert "reconciliation_engine" in settings_obj._saved[0].get("update_fields", [])
