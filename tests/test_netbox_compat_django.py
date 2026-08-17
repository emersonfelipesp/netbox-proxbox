"""NetBox-backed verification of the version-compatibility policy.

The mocked suite (``tests/test_netbox_compat.py``) proves the classification
logic against synthetic versions. This module proves the parts that only a real
NetBox can: that ``ProxboxConfig`` actually sources its bounds from
``netbox_proxbox.compat``, that the NetBox release under test is genuinely
admitted by those bounds, and that Django's real check framework surfaces the
experimental notice as a warning rather than an error.

Run by ``.github/workflows/django-tests.yml`` across the whole NetBox matrix,
so the same assertions are evaluated on every supported release — the 4.5.8 and
4.6.x legs are the backward-compatibility evidence, and the ``v4.7.0-beta1`` leg
is the experimental-support evidence.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
NETBOX_ROOT = REPO_ROOT.parent / "netbox" / "netbox"

for candidate in (REPO_ROOT, NETBOX_ROOT):
    candidate_str = str(candidate)
    if candidate.exists() and candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)

# In CI this is "1", so a broken NetBox harness is a hard failure rather than a
# silent skip — otherwise the whole 4.7 support claim could rest on a job that
# quietly asserted nothing.
_REQUIRE_DJANGO = os.environ.get("NETBOX_PROXBOX_REQUIRE_DJANGO", "").lower() in (
    "1",
    "true",
    "yes",
)

try:
    import django
except ModuleNotFoundError:
    if _REQUIRE_DJANGO:
        raise
    pytest.skip(
        "Django/NetBox test dependencies are not installed in this environment.",
        allow_module_level=True,
    )

os.environ.setdefault("NETBOX_CONFIGURATION", "tests.netbox_test_configuration")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "netbox.settings")

try:
    django.setup()
except Exception as exc:  # pragma: no cover - depends on external test services
    if _REQUIRE_DJANGO:
        raise
    pytest.skip(
        f"NetBox test environment is not available: {exc}", allow_module_level=True
    )

from packaging.version import parse as parse_version  # noqa: E402


def test_plugin_config_sources_its_bounds_from_compat() -> None:
    """Catches the wiring being reverted while ``compat.py`` stays correct."""
    from netbox_proxbox import ProxboxConfig
    from netbox_proxbox.compat import (
        EXPERIMENTAL_MAX_NETBOX_VERSION,
        PLUGIN_MAX_VERSION,
        PLUGIN_MIN_VERSION,
        STABLE_MIN_NETBOX_VERSION,
    )

    assert ProxboxConfig.min_version == PLUGIN_MIN_VERSION == STABLE_MIN_NETBOX_VERSION
    assert (
        ProxboxConfig.max_version == PLUGIN_MAX_VERSION == EXPERIMENTAL_MAX_NETBOX_VERSION
    )


def test_running_netbox_release_is_admitted_by_the_declared_range() -> None:
    """Reproduce NetBox's own gate arithmetic against the release under test.

    On the ``v4.7.0-beta1`` CI leg this is the assertion that fails if the cap
    is ever lowered again: NetBox passes ``RELEASE.version`` (``"4.7.0"``) to
    ``PluginConfig.validate()``, so the ceiling has to cover it.
    """
    from django.conf import settings

    from netbox_proxbox import ProxboxConfig

    current = parse_version(settings.RELEASE.version)
    assert current >= parse_version(ProxboxConfig.min_version)
    assert current <= parse_version(ProxboxConfig.max_version)


def test_detect_netbox_version_matches_the_real_release_metadata() -> None:
    """The comparison/display split must track NetBox's actual RELEASE object."""
    from django.conf import settings

    from netbox_proxbox.compat import detect_netbox_version

    comparison_version, display_version = detect_netbox_version()
    assert comparison_version == settings.RELEASE.version
    assert display_version == settings.RELEASE.full_version


def test_system_check_matches_the_running_release_band() -> None:
    """The registered check must agree with the release actually under test.

    Asserted in both directions so the check cannot pass by being inert: on a
    stable release it must produce nothing, and on an experimental one it must
    produce exactly one ``netbox_proxbox.W001`` warning.
    """
    from django.core.checks import Warning as DjangoWarning
    from django.core.checks import run_checks

    from netbox_proxbox.compat import NetBoxSupportLevel, current_netbox_support_level

    level = current_netbox_support_level()
    messages = [
        message
        for message in run_checks()
        if getattr(message, "id", None) in {"netbox_proxbox.W001", "netbox_proxbox.W002"}
    ]

    if level is NetBoxSupportLevel.EXPERIMENTAL:
        assert len(messages) == 1, f"expected one experimental notice, got {messages}"
        assert messages[0].id == "netbox_proxbox.W001"
        assert isinstance(messages[0], DjangoWarning)
        # A maturity notice must never block startup.
        assert messages[0].level < 40
    else:
        assert messages == [], f"stable release must emit no compatibility notice: {messages}"


def test_plugin_is_actually_installed_and_loaded() -> None:
    """Guards against the whole suite passing while the plugin failed to load.

    If ``PluginConfig.validate()`` had rejected the running NetBox, NetBox would
    not have started at all — but a misconfigured harness could still collect
    these tests. Assert the app registry really has the plugin.
    """
    from django.apps import apps

    assert apps.is_installed("netbox_proxbox")


def test_ready_registered_the_check_by_injecting_a_4_7_release() -> None:
    """An independent oracle for the `ready()` registration itself.

    The band-matching test above cannot catch a deleted registration on a
    *stable* CI cell: its stable branch expects no messages, which is exactly
    what a plugin that never registered anything produces. It also picks its
    expected branch with `current_netbox_support_level()` — the same classifier
    the check itself uses — so both sides move together.

    This test fixes both problems without needing a 4.7 cell. It substitutes
    **literal** 4.7 release metadata (no classifier involved, no version
    arithmetic) and re-runs Django's real check registry. The check being
    exercised is the one `ProxboxConfig.ready()` registered at startup — this test never
    calls the registration function itself — so deleting that call makes this
    fail on every cell, stable ones included.
    """
    from unittest.mock import patch

    from django.conf import settings
    from django.core.checks import run_checks

    class _Release:
        # Transcribed from netbox/release.yaml at tag v4.7.0-beta1; NetBox
        # assembles full_version as version[-designation][-build].
        version = "4.7.0"
        full_version = "4.7.0-beta1"
        designation = "beta1"

    with patch.object(settings, "RELEASE", _Release()):
        messages = [
            message
            for message in run_checks()
            if str(getattr(message, "id", "")) == "netbox_proxbox.W001"
        ]

    assert len(messages) == 1, (
        "ProxboxConfig.ready() must register the compatibility check exactly once; "
        f"got {messages} while pretending to run on NetBox 4.7.0-beta1"
    )
    assert "4.7.0-beta1" in messages[0].msg
    assert "experimental" in messages[0].msg.lower()
    # The pre-release caveat must survive the real registration path too.
    assert "pre-release" in messages[0].msg.lower()


def test_injecting_a_stable_release_produces_no_notice() -> None:
    """The other direction, so the test above cannot pass by always firing."""
    from unittest.mock import patch

    from django.conf import settings
    from django.core.checks import run_checks

    class _Release:
        version = "4.6.4"
        full_version = "4.6.4"
        designation = None

    with patch.object(settings, "RELEASE", _Release()):
        messages = [
            message
            for message in run_checks()
            if str(getattr(message, "id", "")).startswith("netbox_proxbox.W")
        ]

    assert messages == [], f"a stable release must emit nothing; got {messages}"
