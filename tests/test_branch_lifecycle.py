"""Tests for ``netbox_proxbox.services.branch_lifecycle``.

Pins the contract that ``ProxboxSyncJob`` relies on:

* ``branching_enabled_settings()`` returns ``None`` when the plugin flag is off
  or when the optional ``netbox_branching`` plugin is not installed.
* ``branching_enabled_settings()`` returns the ``{"prefix", "on_conflict"}``
  dict otherwise, with defaults applied when persisted fields are blank.
* ``create_and_provision_branch()`` calls ``Branch.save(provision=False)`` and
  then ``Branch.provision(user=...)``, polls ``refresh_from_db`` until status
  becomes ``READY``, and raises ``RuntimeError`` on ``FAILED`` or timeout.
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
    REPO_ROOT
    / "netbox_proxbox"
    / "services"
    / "branch_lifecycle.py"
)


def _install_branching_stubs(
    monkeypatch: pytest.MonkeyPatch,
    *,
    plugin_settings: object,
    available: bool = True,
):
    """Load ``branch_lifecycle.py`` directly with stubbed deps."""

    # Bare parent packages so the qualified module name resolves.
    for name in ("netbox_proxbox", "netbox_proxbox.services"):
        pkg = types.ModuleType(name)
        pkg.__path__ = []  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, name, pkg)

    models_pkg = types.ModuleType("netbox_proxbox.models")

    class _SettingsClass:
        @classmethod
        def get_solo(cls):
            return plugin_settings

    models_pkg.ProxboxPluginSettings = _SettingsClass
    monkeypatch.setitem(sys.modules, "netbox_proxbox.models", models_pkg)

    if available:
        nb = types.ModuleType("netbox_branching")
        monkeypatch.setitem(sys.modules, "netbox_branching", nb)
        nb_choices = types.ModuleType("netbox_branching.choices")

        class _BranchStatusChoices:
            READY = "ready"
            FAILED = "failed"
            NEW = "new"
            PROVISIONING = "provisioning"

        nb_choices.BranchStatusChoices = _BranchStatusChoices
        monkeypatch.setitem(sys.modules, "netbox_branching.choices", nb_choices)
        nb_models = types.ModuleType("netbox_branching.models")
        monkeypatch.setitem(sys.modules, "netbox_branching.models", nb_models)
    else:
        sys.modules.pop("netbox_branching", None)
        sys.modules.pop("netbox_branching.choices", None)
        sys.modules.pop("netbox_branching.models", None)
        monkeypatch.setitem(sys.modules, "netbox_branching", None)

    sys.modules.pop("netbox_proxbox.services.branch_lifecycle", None)
    spec = importlib.util.spec_from_file_location(
        "netbox_proxbox.services.branch_lifecycle",
        BRANCH_LIFECYCLE_PATH,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["netbox_proxbox.services.branch_lifecycle"] = module
    spec.loader.exec_module(module)
    return module


def test_branching_enabled_settings_returns_none_when_flag_off(monkeypatch):
    settings = SimpleNamespace(branching_enabled=False)
    mod = _install_branching_stubs(monkeypatch, plugin_settings=settings)

    assert mod.branching_enabled_settings() is None


def test_branching_enabled_settings_returns_none_when_branching_unavailable(monkeypatch):
    settings = SimpleNamespace(
        branching_enabled=True,
        branch_name_prefix="proxbox-sync",
        branch_on_conflict="fail",
    )
    mod = _install_branching_stubs(
        monkeypatch, plugin_settings=settings, available=False
    )

    assert mod.branching_enabled_settings() is None


def test_branching_enabled_settings_returns_dict_when_enabled(monkeypatch):
    settings = SimpleNamespace(
        branching_enabled=True,
        branch_name_prefix="custom-prefix",
        branch_on_conflict="acknowledge",
    )
    mod = _install_branching_stubs(monkeypatch, plugin_settings=settings)

    assert mod.branching_enabled_settings() == {
        "prefix": "custom-prefix",
        "on_conflict": "acknowledge",
    }


def test_branching_enabled_settings_uses_defaults_for_blank_values(monkeypatch):
    settings = SimpleNamespace(
        branching_enabled=True,
        branch_name_prefix="",
        branch_on_conflict="",
    )
    mod = _install_branching_stubs(monkeypatch, plugin_settings=settings)

    assert mod.branching_enabled_settings() == {
        "prefix": "proxbox-sync",
        "on_conflict": "fail",
    }


def test_branching_enabled_settings_swallows_get_solo_errors(monkeypatch):
    """If the singleton row cannot be loaded, treat branching as disabled."""

    class _Boom:
        @classmethod
        def get_solo(cls):
            raise RuntimeError("db down")

    mod = _install_branching_stubs(monkeypatch, plugin_settings=None)
    # Replace the stubbed ProxboxPluginSettings with one that raises.
    sys.modules["netbox_proxbox.models"].ProxboxPluginSettings = _Boom

    assert mod.branching_enabled_settings() is None


class _FakeBranch:
    """Records save/provision/refresh calls and walks through scripted statuses."""

    def __init__(self, name: str, statuses: list[str]) -> None:
        self.name = name
        self.schema_id = "abcd1234"
        self.status = statuses[0]
        self._statuses = list(statuses)
        self.save_calls: list[dict] = []
        self.provision_calls: list[object | None] = []
        self.refresh_calls = 0

    def save(self, **kwargs):
        self.save_calls.append(kwargs)

    def provision(self, *, user):
        self.provision_calls.append(user)

    def refresh_from_db(self):
        self.refresh_calls += 1
        if len(self._statuses) > 1:
            # Advance the scripted status sequence on each refresh.
            self._statuses.pop(0)
            self.status = self._statuses[0]


def _install_branch_class(monkeypatch, branch_instance):
    """Replace ``netbox_branching.models.Branch`` with a factory yielding our stub."""

    nb_models = sys.modules["netbox_branching.models"]

    def _branch_factory(name):
        branch_instance.name = name
        return branch_instance

    nb_models.Branch = _branch_factory


def test_create_and_provision_branch_polls_until_ready(monkeypatch):
    settings = SimpleNamespace(branching_enabled=True)
    mod = _install_branching_stubs(monkeypatch, plugin_settings=settings)

    branch = _FakeBranch(
        name="placeholder",
        statuses=["new", "provisioning", "ready"],
    )
    _install_branch_class(monkeypatch, branch)
    monkeypatch.setattr(mod.time, "sleep", lambda _: None)

    user = SimpleNamespace(username="op")
    result = mod.create_and_provision_branch(name="b-1", user=user)

    assert result is branch
    assert branch.name == "b-1"
    assert branch.save_calls == [{"provision": False}]
    assert branch.provision_calls == [user]
    assert branch.refresh_calls >= 2


def test_create_and_provision_branch_raises_on_failed(monkeypatch):
    settings = SimpleNamespace(branching_enabled=True)
    mod = _install_branching_stubs(monkeypatch, plugin_settings=settings)

    branch = _FakeBranch(name="placeholder", statuses=["new", "failed"])
    _install_branch_class(monkeypatch, branch)
    monkeypatch.setattr(mod.time, "sleep", lambda _: None)

    with pytest.raises(RuntimeError, match="FAILED"):
        mod.create_and_provision_branch(name="b-fail", user=None)


def test_create_and_provision_branch_times_out(monkeypatch):
    settings = SimpleNamespace(branching_enabled=True)
    mod = _install_branching_stubs(monkeypatch, plugin_settings=settings)

    branch = _FakeBranch(name="placeholder", statuses=["new"])
    _install_branch_class(monkeypatch, branch)
    monkeypatch.setattr(mod.time, "sleep", lambda _: None)

    times = iter([0.0, 0.1, 0.2, 99.0])
    monkeypatch.setattr(mod.time, "monotonic", lambda: next(times))

    with pytest.raises(RuntimeError, match="did not reach READY"):
        mod.create_and_provision_branch(
            name="b-slow", user=None, ready_timeout_seconds=1
        )


def test_create_and_provision_branch_propagates_provision_failure(monkeypatch):
    settings = SimpleNamespace(branching_enabled=True)
    mod = _install_branching_stubs(monkeypatch, plugin_settings=settings)

    class _BoomBranch(_FakeBranch):
        def provision(self, *, user):
            raise RuntimeError("provision boom")

    branch = _BoomBranch(name="placeholder", statuses=["new"])
    _install_branch_class(monkeypatch, branch)
    monkeypatch.setattr(mod.time, "sleep", lambda _: None)

    with pytest.raises(RuntimeError, match="provision boom"):
        mod.create_and_provision_branch(name="b-prov", user=None)
