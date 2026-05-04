"""Tests for encryption settings logic in SettingsView (GET and POST)."""

from __future__ import annotations

import sys
import types
from types import SimpleNamespace

from tests.conftest import load_plugin_module


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BASE_CLEANED_DATA = {
    "use_guest_agent_interface_name": False,
    "proxbox_fetch_max_concurrency": 8,
    "ignore_ipv6_link_local_addresses": False,
    "primary_ip_preference": "ipv4",
    "netbox_max_concurrent": 1,
    "netbox_max_retries": 5,
    "netbox_retry_delay": 2.0,
    "netbox_get_cache_ttl": 60.0,
    "bulk_batch_size": 50,
    "bulk_batch_delay_ms": 500,
    "vm_sync_max_concurrency": 4,
    "custom_fields_request_delay": 0.0,
    "backend_log_file_path": "/var/log/proxbox.log",
    "ssrf_protection_enabled": True,
    "allow_private_ips": True,
    "additional_allowed_ip_ranges": "",
    "explicitly_blocked_ip_ranges": "",
    "proxmox_timeout": 5,
    "proxmox_max_retries": 0,
    "proxmox_retry_backoff": "0.50",
}


def _fake_settings_obj(encryption_key: str = "") -> SimpleNamespace:
    saved: list[dict] = []

    def _save(**kwargs):
        saved.append(kwargs)

    return SimpleNamespace(
        use_guest_agent_interface_name=False,
        proxbox_fetch_max_concurrency=8,
        ignore_ipv6_link_local_addresses=False,
        primary_ip_preference="ipv4",
        netbox_max_concurrent=1,
        netbox_max_retries=5,
        netbox_retry_delay=2.0,
        netbox_get_cache_ttl=60.0,
        bulk_batch_size=50,
        bulk_batch_delay_ms=500,
        vm_sync_max_concurrency=4,
        custom_fields_request_delay=0.0,
        backend_log_file_path="/var/log/proxbox.log",
        ssrf_protection_enabled=True,
        allow_private_ips=True,
        additional_allowed_ip_ranges="",
        explicitly_blocked_ip_ranges="",
        encryption_key=encryption_key,
        proxmox_timeout=5,
        proxmox_max_retries=0,
        proxmox_retry_backoff="0.50",
        overwrite_device_role=True,
        overwrite_device_type=True,
        overwrite_device_tags=True,
        overwrite_device_status=True,
        overwrite_device_description=True,
        overwrite_device_custom_fields=True,
        overwrite_vm_role=True,
        overwrite_vm_type=True,
        overwrite_vm_tags=True,
        overwrite_vm_description=True,
        overwrite_vm_custom_fields=True,
        overwrite_cluster_tags=True,
        overwrite_cluster_description=True,
        overwrite_cluster_custom_fields=True,
        overwrite_node_interface_tags=True,
        overwrite_node_interface_custom_fields=True,
        overwrite_storage_tags=True,
        overwrite_vm_interface_tags=True,
        overwrite_vm_interface_custom_fields=True,
        overwrite_ip_status=True,
        overwrite_ip_tags=True,
        overwrite_ip_custom_fields=True,
        save=_save,
        _saved=saved,
    )


def _fake_form_class(cleaned_data: dict, capture_initial: list | None = None):
    """Return a stub form class whose instances always validate with the given cleaned_data."""

    class _FakeForm:
        def __init__(self, *args, **kwargs):
            if capture_initial is not None:
                capture_initial.append(kwargs.get("initial", {}))

        def is_valid(self):
            return True

        @property
        def cleaned_data(self):
            return cleaned_data

    return _FakeForm


def _load_settings_view(monkeypatch, form_class=None):
    """Load the settings view module, pre-stubbing the forms import."""
    # The view does: from netbox_proxbox.forms.settings import ProxboxPluginSettingsForm
    # netbox_proxbox.forms.settings uses `from django import forms` which isn't stubbed.
    # Pre-register a stub module so the import never touches the real file.
    stub_form_module = types.ModuleType("netbox_proxbox.forms.settings")

    class _DefaultForm:
        def __init__(self, *args, **kwargs):
            pass

    stub_form_module.ProxboxPluginSettingsForm = form_class or _DefaultForm
    monkeypatch.setitem(sys.modules, "netbox_proxbox.forms.settings", stub_form_module)
    return load_plugin_module("netbox_proxbox.views.settings", monkeypatch=monkeypatch)


def _get_request():
    return SimpleNamespace(
        method="GET",
        user=SimpleNamespace(has_perm=lambda *a, **kw: True),
        GET={},
        POST={},
    )


def _post_request():
    return SimpleNamespace(
        method="POST",
        user=SimpleNamespace(has_perm=lambda *a, **kw: True),
        GET={},
        POST={},
    )


# ---------------------------------------------------------------------------
# GET handler: encryption_enabled initial value
# ---------------------------------------------------------------------------


def test_get_populates_encryption_enabled_false_when_key_empty(monkeypatch):
    captured_initial: list[dict] = []
    form_cls = _fake_form_class({}, capture_initial=captured_initial)
    module = _load_settings_view(monkeypatch, form_class=form_cls)

    settings_obj = _fake_settings_obj(encryption_key="")
    monkeypatch.setattr(
        module, "ProxboxPluginSettings", SimpleNamespace(get_solo=lambda: settings_obj)
    )
    monkeypatch.setattr(module, "ProxboxPluginSettingsForm", form_cls)

    module.SettingsView().get(_get_request())

    assert captured_initial, "form constructor must have been called"
    assert captured_initial[0]["encryption_enabled"] is False


def test_get_populates_encryption_enabled_true_when_key_set(monkeypatch):
    captured_initial: list[dict] = []
    form_cls = _fake_form_class({}, capture_initial=captured_initial)
    module = _load_settings_view(monkeypatch, form_class=form_cls)

    settings_obj = _fake_settings_obj(encryption_key="existing-key")
    monkeypatch.setattr(
        module, "ProxboxPluginSettings", SimpleNamespace(get_solo=lambda: settings_obj)
    )
    monkeypatch.setattr(module, "ProxboxPluginSettingsForm", form_cls)

    module.SettingsView().get(_get_request())

    assert captured_initial[0]["encryption_enabled"] is True


# ---------------------------------------------------------------------------
# POST handler: encryption logic
# ---------------------------------------------------------------------------


def test_post_saves_new_key_when_enabled_and_key_provided(monkeypatch):
    cleaned = {
        **_BASE_CLEANED_DATA,
        "encryption_enabled": True,
        "encryption_key": "brand-new-key",
    }
    module = _load_settings_view(monkeypatch, form_class=_fake_form_class(cleaned))

    settings_obj = _fake_settings_obj(encryption_key="")
    monkeypatch.setattr(
        module, "ProxboxPluginSettings", SimpleNamespace(get_solo=lambda: settings_obj)
    )
    monkeypatch.setattr(module, "ProxboxPluginSettingsForm", _fake_form_class(cleaned))

    module.SettingsView().post(_post_request())

    assert settings_obj.encryption_key == "brand-new-key"
    assert settings_obj._saved, "save() must have been called"
    assert "encryption_key" in settings_obj._saved[0].get("update_fields", [])


def test_post_preserves_existing_key_when_enabled_but_key_field_blank(monkeypatch):
    """PasswordInput never pre-fills; submitting blank must not overwrite an existing key."""
    cleaned = {**_BASE_CLEANED_DATA, "encryption_enabled": True, "encryption_key": ""}
    module = _load_settings_view(monkeypatch, form_class=_fake_form_class(cleaned))

    settings_obj = _fake_settings_obj(encryption_key="keep-this-key")
    monkeypatch.setattr(
        module, "ProxboxPluginSettings", SimpleNamespace(get_solo=lambda: settings_obj)
    )
    monkeypatch.setattr(module, "ProxboxPluginSettingsForm", _fake_form_class(cleaned))

    module.SettingsView().post(_post_request())

    assert settings_obj.encryption_key == "keep-this-key"


def test_post_clears_key_when_encryption_disabled(monkeypatch):
    cleaned = {**_BASE_CLEANED_DATA, "encryption_enabled": False, "encryption_key": ""}
    module = _load_settings_view(monkeypatch, form_class=_fake_form_class(cleaned))

    settings_obj = _fake_settings_obj(encryption_key="existing-key")
    monkeypatch.setattr(
        module, "ProxboxPluginSettings", SimpleNamespace(get_solo=lambda: settings_obj)
    )
    monkeypatch.setattr(module, "ProxboxPluginSettingsForm", _fake_form_class(cleaned))

    module.SettingsView().post(_post_request())

    assert settings_obj.encryption_key == ""
    assert settings_obj._saved, "save() must have been called"


def test_post_encryption_key_always_in_update_fields(monkeypatch):
    """encryption_key must be in update_fields so the DB row is always written."""
    cleaned = {
        **_BASE_CLEANED_DATA,
        "encryption_enabled": True,
        "encryption_key": "new-key",
    }
    module = _load_settings_view(monkeypatch, form_class=_fake_form_class(cleaned))

    settings_obj = _fake_settings_obj(encryption_key="")
    monkeypatch.setattr(
        module, "ProxboxPluginSettings", SimpleNamespace(get_solo=lambda: settings_obj)
    )
    monkeypatch.setattr(module, "ProxboxPluginSettingsForm", _fake_form_class(cleaned))

    module.SettingsView().post(_post_request())

    update_fields = settings_obj._saved[0].get("update_fields", [])
    assert "encryption_key" in update_fields
