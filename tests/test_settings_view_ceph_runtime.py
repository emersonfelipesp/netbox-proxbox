"""Tests for Ceph runtime timing round-trip in SettingsView."""

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


def test_get_populates_ceph_runtime_timing(monkeypatch) -> None:
    captured_initial: list[dict[str, object]] = []
    form_cls = _fake_form_class({}, capture_initial=captured_initial)
    module = _load_settings_view(monkeypatch, form_class=form_cls)
    settings_obj = _fake_settings_obj()
    settings_obj.ceph_task_timeout = "420.00"
    settings_obj.ceph_task_poll_interval = "2.50"
    settings_obj.ceph_run_lease_seconds = "600.00"
    monkeypatch.setattr(
        module, "ProxboxPluginSettings", SimpleNamespace(get_solo=lambda: settings_obj)
    )
    monkeypatch.setattr(module, "ProxboxPluginSettingsForm", form_cls)

    module.SettingsView().get(_get_request())

    assert captured_initial[0]["ceph_task_timeout"] == "420.00"
    assert captured_initial[0]["ceph_task_poll_interval"] == "2.50"
    assert captured_initial[0]["ceph_run_lease_seconds"] == "600.00"


def test_post_persists_ceph_runtime_timing(monkeypatch) -> None:
    cleaned = {
        **_BASE_CLEANED_DATA,
        "ceph_task_timeout": "480.00",
        "ceph_task_poll_interval": "3.00",
        "ceph_run_lease_seconds": "720.00",
    }
    form_cls = _fake_form_class(cleaned)
    module = _load_settings_view(monkeypatch, form_class=form_cls)
    settings_obj = _fake_settings_obj()
    monkeypatch.setattr(
        module, "ProxboxPluginSettings", SimpleNamespace(get_solo=lambda: settings_obj)
    )
    monkeypatch.setattr(module, "ProxboxPluginSettingsForm", form_cls)

    module.SettingsView().post(_post_request())

    update_fields = settings_obj._saved[0]["update_fields"]
    assert settings_obj.ceph_task_timeout == "480.00"
    assert settings_obj.ceph_task_poll_interval == "3.00"
    assert settings_obj.ceph_run_lease_seconds == "720.00"
    assert "ceph_task_timeout" in update_fields
    assert "ceph_task_poll_interval" in update_fields
    assert "ceph_run_lease_seconds" in update_fields
