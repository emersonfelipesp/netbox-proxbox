"""Tests for reconciliation-engine settings round-trip in SettingsView."""

from __future__ import annotations

from types import SimpleNamespace

from tests.test_settings_view_encryption import (
    _BASE_CLEANED_DATA,
    _fake_form_class,
    _fake_settings_obj,
    _get_request,
    _load_settings_view,
    _post_request,
)


def _settings_with_engine(
    engine: str = "python", strict: bool = False
) -> SimpleNamespace:
    obj = _fake_settings_obj()
    obj.reconciliation_engine = engine
    obj.reconciliation_compare_strict = strict
    return obj


def test_get_populates_reconciliation_engine_settings(monkeypatch):
    captured_initial: list[dict] = []
    form_cls = _fake_form_class({}, capture_initial=captured_initial)
    module = _load_settings_view(monkeypatch, form_class=form_cls)

    settings_obj = _settings_with_engine("compare", True)
    monkeypatch.setattr(
        module, "ProxboxPluginSettings", SimpleNamespace(get_solo=lambda: settings_obj)
    )
    monkeypatch.setattr(module, "ProxboxPluginSettingsForm", form_cls)

    module.SettingsView().get(_get_request())

    assert captured_initial[0]["reconciliation_engine"] == "compare"
    assert captured_initial[0]["reconciliation_compare_strict"] is True


def test_post_sets_reconciliation_engine_settings_from_cleaned_data(monkeypatch):
    cleaned = {
        **_BASE_CLEANED_DATA,
        "reconciliation_engine": "rust",
        "reconciliation_compare_strict": True,
    }
    module = _load_settings_view(monkeypatch, form_class=_fake_form_class(cleaned))

    settings_obj = _settings_with_engine("python", False)
    monkeypatch.setattr(
        module, "ProxboxPluginSettings", SimpleNamespace(get_solo=lambda: settings_obj)
    )
    monkeypatch.setattr(module, "ProxboxPluginSettingsForm", _fake_form_class(cleaned))

    module.SettingsView().post(_post_request())

    update_fields = settings_obj._saved[0].get("update_fields", [])

    assert settings_obj.reconciliation_engine == "rust"
    assert settings_obj.reconciliation_compare_strict is True
    assert "reconciliation_engine" in update_fields
    assert "reconciliation_compare_strict" in update_fields
