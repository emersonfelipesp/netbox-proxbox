"""Tests for reconciliation-engine settings round-trip in SettingsView."""

from __future__ import annotations

from types import SimpleNamespace

from tests.test_settings_view_encryption import (
    _BASE_CLEANED_DATA,
    _fake_form_class,
    _fake_settings_obj,
    _load_settings_view,
)


def _settings_with_engine(engine: str = "python", strict: bool = False) -> SimpleNamespace:
    obj = _fake_settings_obj()
    obj.reconciliation_engine = engine
    obj.reconciliation_compare_strict = strict
    return obj


def test_get_populates_reconciliation_engine(monkeypatch):
    module = _load_settings_view(monkeypatch)
    settings_obj = _settings_with_engine("compare", True)
    captured_initial = []

    monkeypatch.setattr(
        module.ProxboxPluginSettings,
        "get_solo",
        classmethod(lambda cls: settings_obj),
    )
    monkeypatch.setattr(
        module,
        "ProxboxPluginSettingsForm",
        _fake_form_class({}, capture_initial=captured_initial),
    )
    monkeypatch.setattr(module, "render", lambda request, template, context: context)

    module.SettingsView().get(SimpleNamespace())

    assert captured_initial[0]["reconciliation_engine"] == "compare"
    assert captured_initial[0]["reconciliation_compare_strict"] is True


def test_post_sets_reconciliation_engine(monkeypatch):
    module = _load_settings_view(monkeypatch)
    settings_obj = _settings_with_engine("python", False)
    cleaned = {
        **_BASE_CLEANED_DATA,
        "reconciliation_engine": "rust",
        "reconciliation_compare_strict": True,
    }

    monkeypatch.setattr(
        module.ProxboxPluginSettings,
        "get_solo",
        classmethod(lambda cls: settings_obj),
    )
    monkeypatch.setattr(module, "ProxboxPluginSettingsForm", _fake_form_class(cleaned))
    monkeypatch.setattr(module.messages, "success", lambda *args, **kwargs: None)
    monkeypatch.setattr(module, "redirect", lambda name: name)

    result = module.SettingsView().post(SimpleNamespace(POST={}))

    assert result == "plugins:netbox_proxbox:settings"
    assert settings_obj.reconciliation_engine == "rust"
    assert settings_obj.reconciliation_compare_strict is True
    update_fields = settings_obj._saved[0].get("update_fields", [])
    assert "reconciliation_engine" in update_fields
    assert "reconciliation_compare_strict" in update_fields
