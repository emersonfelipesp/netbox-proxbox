"""Contracts for the UI-configurable Proxbox synchronization job timeout."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from tests.test_settings_view_encryption import (
    _BASE_CLEANED_DATA,
    _fake_form_class,
    _fake_settings_obj,
    _get_request,
    _post_request,
)
from tests.test_settings_view_interface_batch import _load_settings_view

REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text()


def test_sync_job_timeout_is_wired_through_settings_boundaries():
    model = _read("netbox_proxbox/models/plugin_settings.py")
    form = _read("netbox_proxbox/forms/settings.py")
    serializer = _read("netbox_proxbox/api/serializers/settings.py")
    template = _read("netbox_proxbox/templates/netbox_proxbox/settings.html")
    migration = _read(
        "netbox_proxbox/migrations/0103_custom_fields_request_delay_help_text.py"
    )

    assert "sync_job_timeout = models.PositiveIntegerField(" in model
    assert "MinValueValidator(SYNC_JOB_TIMEOUT_MIN)" in model
    assert "MaxValueValidator(SYNC_JOB_TIMEOUT_MAX)" in model
    assert "sync_job_timeout = forms.IntegerField(" in form
    assert "min_value=SYNC_JOB_TIMEOUT_MIN" in form
    assert "max_value=SYNC_JOB_TIMEOUT_MAX" in form
    assert '"sync_job_timeout"' in serializer
    assert "{% render_field form.sync_job_timeout %}" in template
    assert '"sync_job_timeout",' in migration
    assert "default=7200" in migration


def test_settings_get_populates_sync_job_timeout(monkeypatch):
    captured_initial: list[dict] = []
    form_cls = _fake_form_class({}, capture_initial=captured_initial)
    module = _load_settings_view(monkeypatch, form_class=form_cls)
    settings_obj = _fake_settings_obj()
    settings_obj.sync_job_timeout = 14400
    monkeypatch.setattr(
        module, "ProxboxPluginSettings", SimpleNamespace(get_solo=lambda: settings_obj)
    )
    monkeypatch.setattr(module, "ProxboxPluginSettingsForm", form_cls)

    module.SettingsView().get(_get_request())

    assert captured_initial[0]["sync_job_timeout"] == 14400


def test_settings_post_persists_sync_job_timeout(monkeypatch):
    cleaned = {**_BASE_CLEANED_DATA, "sync_job_timeout": 21600}
    form_cls = _fake_form_class(cleaned)
    module = _load_settings_view(monkeypatch, form_class=form_cls)
    settings_obj = _fake_settings_obj()
    monkeypatch.setattr(
        module, "ProxboxPluginSettings", SimpleNamespace(get_solo=lambda: settings_obj)
    )
    monkeypatch.setattr(module, "ProxboxPluginSettingsForm", form_cls)

    module.SettingsView().post(_post_request())

    assert settings_obj.sync_job_timeout == 21600
    assert "sync_job_timeout" in settings_obj._saved[0]["update_fields"]
