"""Tests for optional netbox-bgp integration helpers."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_bgp_module(monkeypatch):
    django_apps = types.ModuleType("django.apps")
    django_apps.apps = types.SimpleNamespace(is_installed=lambda label: False)
    django_mod = types.ModuleType("django")
    django_mod.apps = django_apps
    monkeypatch.setitem(sys.modules, "django", django_mod)
    monkeypatch.setitem(sys.modules, "django.apps", django_apps)

    spec = importlib.util.spec_from_file_location(
        "_netbox_proxbox_integrations_bgp",
        REPO_ROOT / "netbox_proxbox" / "integrations" / "bgp.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_netbox_bgp_status_when_plugin_is_installed(monkeypatch):
    bgp = _load_bgp_module(monkeypatch)
    monkeypatch.setattr(bgp.apps, "is_installed", lambda label: label == "netbox_bgp")

    status = bgp.netbox_bgp_status()

    assert status["installed"] is True
    assert status["plugin"] == "netbox_bgp"
    assert "can run" in str(status["message"])


def test_netbox_bgp_status_when_plugin_is_not_installed(monkeypatch):
    bgp = _load_bgp_module(monkeypatch)
    monkeypatch.setattr(bgp.apps, "is_installed", lambda label: False)

    status = bgp.netbox_bgp_status()

    assert status["installed"] is False
    assert status["plugin"] == "netbox_bgp"
    assert "will be skipped" in str(status["message"])


def test_netbox_bgp_status_handles_missing_django_apps(monkeypatch):
    django_mod = types.ModuleType("django")
    monkeypatch.setitem(sys.modules, "django", django_mod)
    monkeypatch.delitem(sys.modules, "django.apps", raising=False)

    spec = importlib.util.spec_from_file_location(
        "_netbox_proxbox_integrations_bgp_missing_apps",
        REPO_ROOT / "netbox_proxbox" / "integrations" / "bgp.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    status = module.netbox_bgp_status()

    assert status["installed"] is False
    assert "will be skipped" in str(status["message"])
