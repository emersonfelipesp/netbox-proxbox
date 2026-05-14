"""Tests for ``netbox_ceph.services.branch_lifecycle``.

The Ceph plugin reuses ``netbox_proxbox.services.branch_lifecycle`` for
all Branch provisioning/conflict/merge mechanics and only overrides the
policy lookup to read ``CephPluginSettings``. Pins:

* ``branching_enabled_settings()`` reads ``CephPluginSettings.get_solo()``
  not ``ProxboxPluginSettings``.
* Returns ``None`` when ``branching_enabled`` is ``False`` or
  ``netbox_branching`` is not installed.
* Falls back to default prefix ``"ceph-sync"`` / on_conflict ``"fail"``
  when the persisted fields are blank.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import types
from types import SimpleNamespace

import pytest


REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
BRANCH_LIFECYCLE_PATH = (
    REPO_ROOT / "netbox_ceph" / "netbox_ceph" / "services" / "branch_lifecycle.py"
)


def _install_branch_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
    *,
    plugin_settings: object,
    netbox_branching_available: bool = True,
):
    for name in (
        "netbox_ceph",
        "netbox_ceph.models",
        "netbox_proxbox",
        "netbox_proxbox.services",
        "netbox_proxbox.services.branch_lifecycle",
    ):
        pkg = types.ModuleType(name)
        pkg.__path__ = []  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, name, pkg)

    models_pkg = sys.modules["netbox_ceph.models"]

    class _SettingsClass:
        @classmethod
        def get_solo(cls):
            return plugin_settings

    models_pkg.CephPluginSettings = _SettingsClass  # type: ignore[attr-defined]

    upstream = sys.modules["netbox_proxbox.services.branch_lifecycle"]

    def _is_branching_available() -> bool:
        return netbox_branching_available

    upstream.is_branching_available = _is_branching_available  # type: ignore[attr-defined]

    def _stub(*_a, **_k):  # pragma: no cover - safety net for unused re-exports
        return None

    upstream.branch_has_conflicts = _stub  # type: ignore[attr-defined]
    upstream.create_and_provision_branch = _stub  # type: ignore[attr-defined]
    upstream.get_active_branch_schema_id = _stub  # type: ignore[attr-defined]
    upstream.merge_branch = _stub  # type: ignore[attr-defined]

    sys.modules.pop("netbox_ceph.services.branch_lifecycle", None)
    spec = importlib.util.spec_from_file_location(
        "netbox_ceph.services.branch_lifecycle",
        BRANCH_LIFECYCLE_PATH,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["netbox_ceph.services.branch_lifecycle"] = module
    spec.loader.exec_module(module)
    return module


def test_returns_none_when_branching_disabled(monkeypatch):
    settings = SimpleNamespace(branching_enabled=False)
    mod = _install_branch_lifecycle(monkeypatch, plugin_settings=settings)
    assert mod.branching_enabled_settings() is None


def test_returns_none_when_branching_unavailable(monkeypatch):
    settings = SimpleNamespace(
        branching_enabled=True,
        branch_name_prefix="ceph-sync",
        branch_on_conflict="fail",
    )
    mod = _install_branch_lifecycle(
        monkeypatch, plugin_settings=settings, netbox_branching_available=False
    )
    assert mod.branching_enabled_settings() is None


def test_returns_policy_dict_when_enabled(monkeypatch):
    settings = SimpleNamespace(
        branching_enabled=True,
        branch_name_prefix="ceph-night",
        branch_on_conflict="acknowledge",
    )
    mod = _install_branch_lifecycle(monkeypatch, plugin_settings=settings)
    assert mod.branching_enabled_settings() == {
        "prefix": "ceph-night",
        "on_conflict": "acknowledge",
    }


def test_falls_back_to_defaults_when_fields_blank(monkeypatch):
    settings = SimpleNamespace(
        branching_enabled=True,
        branch_name_prefix="",
        branch_on_conflict="",
    )
    mod = _install_branch_lifecycle(monkeypatch, plugin_settings=settings)
    assert mod.branching_enabled_settings() == {
        "prefix": "ceph-sync",
        "on_conflict": "fail",
    }
