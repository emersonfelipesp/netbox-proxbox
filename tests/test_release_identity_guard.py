"""Regression tests for the retired held-beta runtime hook."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_compat_module():
    spec = importlib.util.spec_from_file_location(
        "netbox_compat_release_hook_under_test", ROOT / "netbox_proxbox/compat.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_legacy_release_identity_hook_is_a_noop() -> None:
    """GA admission uses numeric bounds and never reads release metadata."""
    compat = _load_compat_module()

    class PluginConfig:
        pass

    compat.validate_held_netbox_release_identity(PluginConfig, "4.7.0")
    compat.validate_held_netbox_release_identity(PluginConfig, "4.7.0-beta2")


def test_ga_version_is_stable_and_declared_ceiling_covers_minor_line() -> None:
    compat = _load_compat_module()

    assert compat.netbox_support_level("4.7.0").value == "stable"
    assert compat.netbox_support_level("4.7.99").value == "stable"
    assert compat.PLUGIN_MIN_VERSION == "4.5.8"
    assert compat.PLUGIN_MAX_VERSION == "4.7.99"
