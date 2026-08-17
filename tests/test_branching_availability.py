"""`is_branching_available()` must require a loaded app, not an importable package.

`netboxlabs-netbox-branching` declares `max_version = "4.6.99"`. NetBox handles
an out-of-range plugin by catching `IncompatiblePluginError`, warning, and
*skipping* it — so on NetBox 4.7 the package stays importable while its Django
app is absent from `INSTALLED_APPS` and its models and schemas do not exist.

An import-only check reports "available" in exactly that state, and callers then
create branches against an engine that is not running. These tests pin the
distinction, because it is invisible until a NetBox version skips the app.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from typing import Any

import pytest


def _load_branch_lifecycle(apps_module: Any, branching_importable: bool) -> Any:
    """Load the module against a controlled `django.apps` and package presence."""
    module_path = (
        Path(__file__).resolve().parents[1]
        / "netbox_proxbox"
        / "services"
        / "branch_lifecycle.py"
    )
    spec = importlib.util.spec_from_file_location(
        "branch_lifecycle_under_test", module_path
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # branch_lifecycle imports netbox_proxbox.models at module scope, which
    # reaches netbox.plugins. Stub the package chain so the module loads without
    # a real NetBox; only is_branching_available() is under test here.
    names = (
        "django",
        "django.apps",
        "netbox_branching",
        "netbox_proxbox",
        "netbox_proxbox.models",
    )
    saved = {name: sys.modules.get(name) for name in names}
    try:
        django_mod = types.ModuleType("django")
        django_mod.__path__ = []  # type: ignore[attr-defined]
        sys.modules["django"] = django_mod
        sys.modules["django.apps"] = apps_module

        proxbox_pkg = types.ModuleType("netbox_proxbox")
        proxbox_pkg.__path__ = []  # type: ignore[attr-defined]
        models_mod = types.ModuleType("netbox_proxbox.models")
        models_mod.ProxboxPluginSettings = type("ProxboxPluginSettings", (), {})
        sys.modules["netbox_proxbox"] = proxbox_pkg
        sys.modules["netbox_proxbox.models"] = models_mod

        if branching_importable:
            sys.modules["netbox_branching"] = types.ModuleType("netbox_branching")
        else:
            sys.modules.pop("netbox_branching", None)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module.is_branching_available()
    finally:
        sys.modules.pop(spec.name, None)
        for name, previous in saved.items():
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous


def _apps(installed: bool | Exception) -> Any:
    mod = types.ModuleType("django.apps")

    class _Apps:
        def is_installed(self, label: str) -> bool:
            assert label == "netbox_branching"
            if isinstance(installed, Exception):
                raise installed
            return installed

    mod.apps = _Apps()  # type: ignore[attr-defined]
    return mod


def test_available_when_the_app_is_loaded() -> None:
    assert _load_branch_lifecycle(_apps(True), branching_importable=True) is True


def test_unavailable_when_the_app_was_skipped_but_the_package_imports() -> None:
    """The NetBox 4.7 state. An import-only check gets this one wrong."""
    assert _load_branch_lifecycle(_apps(False), branching_importable=True) is False


def test_unavailable_when_the_package_is_absent() -> None:
    assert _load_branch_lifecycle(_apps(False), branching_importable=False) is False


def test_a_registry_failure_is_reported_as_unavailable() -> None:
    """Callers treat False as "stay on main"; detection must not raise."""
    assert (
        _load_branch_lifecycle(
            _apps(RuntimeError("apps not ready")), branching_importable=True
        )
        is False
    )
