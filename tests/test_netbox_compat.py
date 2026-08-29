"""Tests for the NetBox version-compatibility policy in ``netbox_proxbox.compat``.

Covers the four support bands, the beta version-string handling that motivated
raising the version cap, version detection, and the Django system check.

``compat.py`` is loaded **by file path** rather than through
``netbox_proxbox/__init__.py``, matching the convention the rest of the mocked
suite uses: the package ``__init__`` imports ``netbox.plugins``, which only
exists under a real NetBox. That is also a genuine property worth holding —
``compat.py`` deliberately imports nothing but the standard library and
``packaging`` at module scope, because NetBox imports it while
``netbox/settings.py`` is still executing.

The Django-dependent paths inject their own ``django.conf`` /
``django.core.checks`` modules, so they behave identically with or without a
real Django present.

``ProxboxConfig``'s actual wiring is verified in
``tests/test_netbox_compat_django.py`` against real NetBox.
"""

from __future__ import annotations

import importlib.util
import logging
import sys
import types
from pathlib import Path
from typing import Any

import pytest
from packaging.version import InvalidVersion, parse as parse_version

# ---------------------------------------------------------------------------
# Facts transcribed once from upstream NetBox, deliberately NOT derived from
# the module under test. netbox/release.yaml at tag v4.7.0-beta1 reads:
#
#     version: "4.7.0"
#     designation: "beta1"
#
# and netbox/netbox/settings.py calls
# `plugin_config.validate(PLUGINS_CONFIG[plugin_name], RELEASE.version)`.
# So the plugin gate compares against the bare "4.7.0" while operators see
# "4.7.0-beta1". If either stops being true upstream, these tests must fail
# rather than quietly track the change.
# ---------------------------------------------------------------------------
NETBOX_470_BETA1_COMPARISON_VERSION = "4.7.0"
NETBOX_470_BETA1_DISPLAY_VERSION = "4.7.0-beta1"


def _load_compat_module() -> Any:
    """Load ``netbox_proxbox/compat.py`` without importing the plugin package."""
    module_path = Path(__file__).resolve().parents[1] / "netbox_proxbox" / "compat.py"
    spec = importlib.util.spec_from_file_location(
        "netbox_compat_under_test", module_path
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


compat = _load_compat_module()

NetBoxSupportLevel = compat.NetBoxSupportLevel
netbox_support_level = compat.netbox_support_level
detect_netbox_version = compat.detect_netbox_version
experimental_warning_message = compat.experimental_warning_message
register_netbox_compatibility_check = compat.register_netbox_compatibility_check
is_prerelease_netbox = compat.is_prerelease_netbox
detect_netbox_designation = compat.detect_netbox_designation
SILENCE_SETTING_NAME = compat.SILENCE_SETTING_NAME

STABLE_MIN_NETBOX_VERSION = compat.STABLE_MIN_NETBOX_VERSION
STABLE_MAX_NETBOX_VERSION = compat.STABLE_MAX_NETBOX_VERSION
EXPERIMENTAL_MIN_NETBOX_VERSION = compat.EXPERIMENTAL_MIN_NETBOX_VERSION
EXPERIMENTAL_MAX_NETBOX_VERSION = compat.EXPERIMENTAL_MAX_NETBOX_VERSION
PLUGIN_MIN_VERSION = compat.PLUGIN_MIN_VERSION
PLUGIN_MAX_VERSION = compat.PLUGIN_MAX_VERSION
CONTRACT_VERSION = compat.CONTRACT_VERSION


class _FakeRelease:
    def __init__(self, version: str, full_version: str) -> None:
        self.version = version
        self.full_version = full_version


class _FakeAppConfig:
    def __init__(
        self, label: str = "netbox_proxbox", verbose_name: str = "Proxbox"
    ) -> None:
        self.label = label
        self.name = label
        self.verbose_name = verbose_name


def _install_fake_django(
    monkeypatch: pytest.MonkeyPatch, settings_obj: Any
) -> list[Any]:
    """Install minimal ``django.conf`` / ``django.core.checks`` modules.

    Returns the list registered system-check callables are appended to, so a
    test can invoke the registered check directly.
    """
    registered: list[Any] = []

    django_mod = types.ModuleType("django")
    django_mod.__path__ = []  # type: ignore[attr-defined]

    conf_mod = types.ModuleType("django.conf")
    conf_mod.settings = settings_obj  # type: ignore[attr-defined]

    core_mod = types.ModuleType("django.core")
    core_mod.__path__ = []  # type: ignore[attr-defined]

    checks_mod = types.ModuleType("django.core.checks")

    class _CheckMessage:
        def __init__(
            self, msg: str, hint: str | None = None, id: str | None = None
        ) -> None:
            self.msg = msg
            self.hint = hint
            self.id = id

    # Mirrors Django's own severity levels. Both are provided so that a
    # regression to Error fails on the *assertion* below rather than blowing up
    # with AttributeError, which would be a much less legible failure.
    class Warning(_CheckMessage):  # noqa: A001 — deliberately shadows the builtin
        level = 30

    class Error(_CheckMessage):
        level = 40

    checks_mod.Warning = Warning  # type: ignore[attr-defined]
    checks_mod.Error = Error  # type: ignore[attr-defined]
    checks_mod.register = registered.append  # type: ignore[attr-defined]

    for name, module in (
        ("django", django_mod),
        ("django.conf", conf_mod),
        ("django.core", core_mod),
        ("django.core.checks", checks_mod),
    ):
        monkeypatch.setitem(sys.modules, name, module)

    return registered


def _reset_registration_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clear the module-level dedupe set so each test starts from a clean slate."""
    monkeypatch.setattr(compat, "_REGISTERED_APP_LABELS", set())


def _run_registered_check(registered: list[Any]) -> list[Any]:
    assert len(registered) == 1, "expected exactly one registered system check"
    return registered[0](app_configs=None)


# ---------------------------------------------------------------------------
# Module-scope import hygiene
# ---------------------------------------------------------------------------


def test_compat_imports_no_django_at_module_scope() -> None:
    """NetBox imports this module while settings.py is still executing.

    A module-scope Django import (or worse, a settings *read*) would run before
    Django is configured. The load above already proves it: it succeeded with
    no Django stubs installed.
    """
    source = (
        Path(__file__).resolve().parents[1] / "netbox_proxbox" / "compat.py"
    ).read_text()
    module_scope_lines = [
        line
        for line in source.splitlines()
        if (line.startswith("import ") or line.startswith("from ")) and "django" in line
    ]
    assert module_scope_lines == []


# ---------------------------------------------------------------------------
# Support-band classification
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("netbox_version", "expected"),
    [
        # Below the floor — the stock PluginConfig gate refuses these.
        ("4.0.0", "unsupported-old"),
        ("4.5.7", "unsupported-old"),
        # Certified, CI-gated band.
        ("4.5.8", "stable"),
        ("4.5.10", "stable"),
        ("4.6.0", "stable"),
        ("4.6.4", "stable"),
        ("4.6.6", "stable"),
        ("4.6.99", "stable"),
        # Numeric held line. The separate canonical identity guard narrows
        # this bare value to beta2.
        ("4.7.0", "experimental"),
        ("4.7.0-beta1", "experimental"),
        ("4.7.0b1", "experimental"),
        # Above the exact bare 4.7.0 ceiling — refused again.
        ("4.7.3", "unsupported-new"),
        ("4.7.99", "unsupported-new"),
        ("4.8.0", "unsupported-new"),
        ("5.0.0", "unsupported-new"),
    ],
)
def test_netbox_support_level_classifies_every_band(
    netbox_version: str, expected: str
) -> None:
    assert netbox_support_level(netbox_version).value == expected


def test_band_boundaries_are_exact() -> None:
    """The bands must abut with no gap and no overlap."""
    assert netbox_support_level(STABLE_MIN_NETBOX_VERSION) is NetBoxSupportLevel.STABLE
    assert netbox_support_level(STABLE_MAX_NETBOX_VERSION) is NetBoxSupportLevel.STABLE
    assert (
        netbox_support_level(EXPERIMENTAL_MIN_NETBOX_VERSION)
        is NetBoxSupportLevel.EXPERIMENTAL
    )
    assert (
        netbox_support_level(EXPERIMENTAL_MAX_NETBOX_VERSION)
        is NetBoxSupportLevel.EXPERIMENTAL
    )
    assert parse_version(STABLE_MAX_NETBOX_VERSION) < parse_version(
        EXPERIMENTAL_MIN_NETBOX_VERSION
    )


def test_unparseable_version_raises_rather_than_defaulting_to_supported() -> None:
    """A version we cannot classify must fail loudly, not fall through to 'stable'."""
    with pytest.raises(InvalidVersion):
        netbox_support_level("not-a-version")


# ---------------------------------------------------------------------------
# The reason the cap moved: beta release strings
# ---------------------------------------------------------------------------


def test_plugin_gate_admits_the_470_beta1_comparison_string() -> None:
    """Reproduce NetBox's own gate arithmetic against the real beta version.

    ``PluginConfig.validate()`` does
    ``version.parse(netbox_version) > version.parse(max_version)``. This asserts
    the declared ceiling actually admits what NetBox will pass in.
    """
    current = parse_version(NETBOX_470_BETA1_COMPARISON_VERSION)
    assert current >= parse_version(PLUGIN_MIN_VERSION)
    assert current <= parse_version(PLUGIN_MAX_VERSION)


def test_the_previous_ceiling_would_have_rejected_470_beta1() -> None:
    """Guard the guard: prove 4.6.99 really was the blocker being removed."""
    assert parse_version(NETBOX_470_BETA1_COMPARISON_VERSION) > parse_version("4.6.99")


def test_comparison_and_display_strings_classify_identically() -> None:
    """Whichever form reaches the classifier, the verdict must be the same."""
    assert (
        netbox_support_level(NETBOX_470_BETA1_COMPARISON_VERSION)
        is netbox_support_level(NETBOX_470_BETA1_DISPLAY_VERSION)
        is NetBoxSupportLevel.EXPERIMENTAL
    )


def test_declared_bounds_have_the_expected_literal_values() -> None:
    """Pins the shared contract so a silent band change fails here."""
    assert STABLE_MIN_NETBOX_VERSION == "4.5.8"
    assert STABLE_MAX_NETBOX_VERSION == "4.6.99"
    assert EXPERIMENTAL_MIN_NETBOX_VERSION == "4.7.0"
    assert EXPERIMENTAL_MAX_NETBOX_VERSION == "4.7.0"
    assert PLUGIN_MIN_VERSION == STABLE_MIN_NETBOX_VERSION
    assert PLUGIN_MAX_VERSION == EXPERIMENTAL_MAX_NETBOX_VERSION
    assert CONTRACT_VERSION == "netbox-compat-v3"


# ---------------------------------------------------------------------------
# Version detection
# ---------------------------------------------------------------------------


def test_detect_netbox_version_splits_comparison_from_display(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = types.SimpleNamespace(
        RELEASE=_FakeRelease(
            NETBOX_470_BETA1_COMPARISON_VERSION, NETBOX_470_BETA1_DISPLAY_VERSION
        ),
        VERSION=NETBOX_470_BETA1_DISPLAY_VERSION,
    )
    _install_fake_django(monkeypatch, settings)

    assert detect_netbox_version() == (
        NETBOX_470_BETA1_COMPARISON_VERSION,
        NETBOX_470_BETA1_DISPLAY_VERSION,
    )


def test_detect_netbox_version_falls_back_to_settings_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = types.SimpleNamespace(RELEASE=None, VERSION="4.6.4")
    _install_fake_django(monkeypatch, settings)

    assert detect_netbox_version() == ("4.6.4", "4.6.4")


def test_detect_netbox_version_raises_when_nothing_is_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = types.SimpleNamespace(RELEASE=None, VERSION=None)
    _install_fake_django(monkeypatch, settings)

    with pytest.raises(RuntimeError):
        detect_netbox_version()


# ---------------------------------------------------------------------------
# System check behaviour
# ---------------------------------------------------------------------------


def test_experimental_version_emits_exactly_one_warning(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _reset_registration_guard(monkeypatch)
    settings = types.SimpleNamespace(
        RELEASE=_FakeRelease(
            NETBOX_470_BETA1_COMPARISON_VERSION, NETBOX_470_BETA1_DISPLAY_VERSION
        ),
        VERSION=NETBOX_470_BETA1_DISPLAY_VERSION,
    )
    registered = _install_fake_django(monkeypatch, settings)

    with caplog.at_level(logging.WARNING):
        register_netbox_compatibility_check(
            _FakeAppConfig(), logging.getLogger("test.compat")
        )

    results = _run_registered_check(registered)
    assert len(results) == 1
    assert results[0].id == "netbox_proxbox.W001"
    # A maturity notice must never be an Error — that would block startup.
    assert type(results[0]).__name__ == "Warning"
    assert results[0].level == 30
    assert NETBOX_470_BETA1_DISPLAY_VERSION in results[0].msg
    assert SILENCE_SETTING_NAME in (results[0].hint or "")

    # And the same notice reaches operators who never run `manage.py check`.
    assert any(
        NETBOX_470_BETA1_DISPLAY_VERSION in record.getMessage()
        for record in caplog.records
    )


@pytest.mark.parametrize("stable_version", ["4.5.8", "4.6.0", "4.6.4", "4.6.99"])
def test_stable_versions_emit_no_warning_at_all(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    stable_version: str,
) -> None:
    """Backward compatibility: existing installs must see no new noise."""
    _reset_registration_guard(monkeypatch)
    settings = types.SimpleNamespace(
        RELEASE=_FakeRelease(stable_version, stable_version), VERSION=stable_version
    )
    registered = _install_fake_django(monkeypatch, settings)

    with caplog.at_level(logging.WARNING):
        register_netbox_compatibility_check(
            _FakeAppConfig(), logging.getLogger("test.compat")
        )

    assert _run_registered_check(registered) == []
    assert caplog.records == []


def test_undeterminable_version_reports_w002_instead_of_passing_silently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A check that cannot evaluate must say so, not report success."""
    _reset_registration_guard(monkeypatch)
    settings = types.SimpleNamespace(RELEASE=None, VERSION=None)
    registered = _install_fake_django(monkeypatch, settings)

    register_netbox_compatibility_check(
        _FakeAppConfig(), logging.getLogger("test.compat")
    )

    results = _run_registered_check(registered)
    assert len(results) == 1
    assert results[0].id == "netbox_proxbox.W002"


def test_registration_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    """A second ready() must not double the operator-facing warning."""
    _reset_registration_guard(monkeypatch)
    settings = types.SimpleNamespace(
        RELEASE=_FakeRelease(
            NETBOX_470_BETA1_COMPARISON_VERSION, NETBOX_470_BETA1_DISPLAY_VERSION
        ),
        VERSION=NETBOX_470_BETA1_DISPLAY_VERSION,
    )
    registered = _install_fake_django(monkeypatch, settings)

    register_netbox_compatibility_check(
        _FakeAppConfig(), logging.getLogger("test.compat")
    )
    register_netbox_compatibility_check(
        _FakeAppConfig(), logging.getLogger("test.compat")
    )

    assert len(registered) == 1


def test_experimental_warning_message_names_the_certified_range() -> None:
    message = experimental_warning_message("Proxbox", NETBOX_470_BETA1_DISPLAY_VERSION)
    assert "Proxbox" in message
    assert NETBOX_470_BETA1_DISPLAY_VERSION in message
    assert STABLE_MIN_NETBOX_VERSION in message
    assert STABLE_MAX_NETBOX_VERSION in message


# ---------------------------------------------------------------------------
# Pre-release maturity caveat
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("display_version", "expected"),
    [
        ("4.7.0-beta1", True),
        ("4.7.0b1", True),
        ("4.7.0-rc1", True),
        ("4.7.0", False),
        ("4.7.2", False),
        ("4.6.4", False),
        # Must not raise: this only decorates a warning.
        ("not-a-version", False),
        # NetBox builds full_version as version[-designation][-build], so a
        # container image reports a string packaging rejects outright. A naive
        # parse returns False here and silently drops the pre-release caveat on
        # every containerised install — the deployment most likely to be running
        # a beta in the first place.
        ("4.7.0-beta1-Docker-3.4.0", True),
        ("4.7.0-rc1-Docker-3.4.0", True),
        ("4.7.0-Docker-3.4.0", False),
        ("4.6.4-Docker-3.3.0", False),
    ],
)
def test_prerelease_detection(display_version: str, expected: bool) -> None:
    assert is_prerelease_netbox(display_version) is expected


@pytest.mark.parametrize(
    ("display_version", "designation", "expected"),
    [
        # The designation is authoritative: NetBox leaves it unset on a stable
        # release, so any value means pre-release regardless of the string.
        ("4.7.0-Docker-3.4.0", "beta1", True),
        ("totally unparseable", "rc2", True),
        ("4.7.0", None, False),
        ("4.7.0", "", False),
    ],
)
def test_designation_overrides_string_parsing(
    display_version: str, designation: str | None, expected: bool
) -> None:
    assert is_prerelease_netbox(display_version, designation) is expected


def test_prerelease_detection_terminates_on_pathological_input() -> None:
    """The suffix-stripping loop is bounded; a dash storm must not hang."""
    assert is_prerelease_netbox("-" * 500) is False
    assert is_prerelease_netbox("a-" * 500) is False


def test_prerelease_warning_states_the_upstream_restriction() -> None:
    """A beta is a different risk from an uncertified-but-stable release.

    Upstream does not support pre-releases in production and gives no upgrade
    path from a pre-release to GA, so the notice must say so rather than leave
    an operator with only the word "experimental".
    """
    message = experimental_warning_message("Proxbox", NETBOX_470_BETA1_DISPLAY_VERSION)
    lowered = message.lower()
    assert "pre-release" in lowered
    assert "production" in lowered
    assert "upgrade path" in lowered


def test_stable_experimental_release_gets_no_prerelease_caveat() -> None:
    """A hypothetical 4.7.2 GA is experimental, but not a pre-release."""
    message = experimental_warning_message("Proxbox", "4.7.2")
    assert "pre-release" not in message.lower()
    assert "experimental basis only" in message


def test_prerelease_hint_does_not_read_as_production_clearance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_registration_guard(monkeypatch)
    settings = types.SimpleNamespace(
        RELEASE=_FakeRelease(
            NETBOX_470_BETA1_COMPARISON_VERSION, NETBOX_470_BETA1_DISPLAY_VERSION
        ),
        VERSION=NETBOX_470_BETA1_DISPLAY_VERSION,
    )
    registered = _install_fake_django(monkeypatch, settings)

    register_netbox_compatibility_check(
        _FakeAppConfig(), logging.getLogger("test.compat")
    )

    hint = _run_registered_check(registered)[0].hint or ""
    assert SILENCE_SETTING_NAME in hint
    # Silencing the check must not be presented as lifting upstream's restriction.
    assert "does not\n" not in hint and "does not lift it" in hint
    assert "fully operational" not in hint


# ---------------------------------------------------------------------------
# SILENCED_SYSTEM_CHECKS suppresses BOTH surfaces
# ---------------------------------------------------------------------------


def test_silencing_the_check_also_silences_the_startup_log(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """One documented action must silence both surfaces, not just the check.

    Django's SILENCED_SYSTEM_CHECKS only suppresses the check framework's
    output. The ready() log line is ours, so it has to consult the same setting
    — otherwise an operator who accepted the risk still gets the warning in
    every process's startup log forever, and the documented procedure is a lie.
    """
    _reset_registration_guard(monkeypatch)
    settings = types.SimpleNamespace(
        RELEASE=_FakeRelease(
            NETBOX_470_BETA1_COMPARISON_VERSION, NETBOX_470_BETA1_DISPLAY_VERSION
        ),
        VERSION=NETBOX_470_BETA1_DISPLAY_VERSION,
        SILENCED_SYSTEM_CHECKS=["netbox_proxbox.W001"],
    )
    _install_fake_django(monkeypatch, settings)

    with caplog.at_level(logging.WARNING):
        register_netbox_compatibility_check(
            _FakeAppConfig(), logging.getLogger("test.compat")
        )

    assert caplog.records == []


def test_silencing_a_different_check_does_not_silence_ours(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Guard the guard: the suppression must be keyed on our own id."""
    _reset_registration_guard(monkeypatch)
    settings = types.SimpleNamespace(
        RELEASE=_FakeRelease(
            NETBOX_470_BETA1_COMPARISON_VERSION, NETBOX_470_BETA1_DISPLAY_VERSION
        ),
        VERSION=NETBOX_470_BETA1_DISPLAY_VERSION,
        SILENCED_SYSTEM_CHECKS=["some_other_plugin.W001", "netbox_proxbox.W002"],
    )
    _install_fake_django(monkeypatch, settings)

    with caplog.at_level(logging.WARNING):
        register_netbox_compatibility_check(
            _FakeAppConfig(), logging.getLogger("test.compat")
        )

    assert len(caplog.records) == 1


def test_a_missing_silenced_setting_still_shows_the_notice(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Suppression fails open — an unreadable setting must not hide the notice."""
    _reset_registration_guard(monkeypatch)
    settings = types.SimpleNamespace(
        RELEASE=_FakeRelease(
            NETBOX_470_BETA1_COMPARISON_VERSION, NETBOX_470_BETA1_DISPLAY_VERSION
        ),
        VERSION=NETBOX_470_BETA1_DISPLAY_VERSION,
    )  # no SILENCED_SYSTEM_CHECKS attribute at all
    _install_fake_django(monkeypatch, settings)

    with caplog.at_level(logging.WARNING):
        register_netbox_compatibility_check(
            _FakeAppConfig(), logging.getLogger("test.compat")
        )

    assert len(caplog.records) == 1


# ---------------------------------------------------------------------------
# PLUGINS_CONFIG is the *supported* suppression path
# ---------------------------------------------------------------------------


def test_plugins_config_silences_both_surfaces(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """NetBox does not import SILENCED_SYSTEM_CHECKS from configuration.py.

    `settings.py` pulls an explicit list of named settings via
    `getattr(configuration, ...)`, and that one is not on it — so an operator
    who sets it there changes nothing. `PLUGINS_CONFIG` *is* imported, so the
    per-plugin key has to work, and it has to silence the system check as well
    as the log line: Django's framework only honours its own setting, so the
    check function must apply this opt-out itself.
    """
    _reset_registration_guard(monkeypatch)
    settings = types.SimpleNamespace(
        RELEASE=_FakeRelease(
            NETBOX_470_BETA1_COMPARISON_VERSION, NETBOX_470_BETA1_DISPLAY_VERSION
        ),
        VERSION=NETBOX_470_BETA1_DISPLAY_VERSION,
        PLUGINS_CONFIG={"netbox_proxbox": {SILENCE_SETTING_NAME: True}},
    )
    registered = _install_fake_django(monkeypatch, settings)

    with caplog.at_level(logging.WARNING):
        register_netbox_compatibility_check(
            _FakeAppConfig(), logging.getLogger("test.compat")
        )

    assert caplog.records == [], "the ready() log line was not silenced"
    assert _run_registered_check(registered) == [], "the system check was not silenced"


def test_plugins_config_opt_out_is_keyed_to_this_plugin(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Another plugin's opt-out must not silence ours."""
    _reset_registration_guard(monkeypatch)
    settings = types.SimpleNamespace(
        RELEASE=_FakeRelease(
            NETBOX_470_BETA1_COMPARISON_VERSION, NETBOX_470_BETA1_DISPLAY_VERSION
        ),
        VERSION=NETBOX_470_BETA1_DISPLAY_VERSION,
        PLUGINS_CONFIG={"some_other_plugin": {SILENCE_SETTING_NAME: True}},
    )
    registered = _install_fake_django(monkeypatch, settings)

    with caplog.at_level(logging.WARNING):
        register_netbox_compatibility_check(
            _FakeAppConfig(), logging.getLogger("test.compat")
        )

    assert len(caplog.records) == 1
    assert len(_run_registered_check(registered)) == 1


@pytest.mark.parametrize("falsy", [False, None, 0, ""])
def test_a_falsy_opt_out_still_shows_the_notice(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, falsy: object
) -> None:
    """Suppression requires an affirmative value; anything else fails open."""
    _reset_registration_guard(monkeypatch)
    settings = types.SimpleNamespace(
        RELEASE=_FakeRelease(
            NETBOX_470_BETA1_COMPARISON_VERSION, NETBOX_470_BETA1_DISPLAY_VERSION
        ),
        VERSION=NETBOX_470_BETA1_DISPLAY_VERSION,
        PLUGINS_CONFIG={"netbox_proxbox": {SILENCE_SETTING_NAME: falsy}},
    )
    registered = _install_fake_django(monkeypatch, settings)

    with caplog.at_level(logging.WARNING):
        register_netbox_compatibility_check(
            _FakeAppConfig(), logging.getLogger("test.compat")
        )

    assert len(caplog.records) == 1
    assert len(_run_registered_check(registered)) == 1


def test_a_malformed_plugins_config_entry_fails_open(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A junk entry must not crash startup, and must not hide the notice."""
    _reset_registration_guard(monkeypatch)
    settings = types.SimpleNamespace(
        RELEASE=_FakeRelease(
            NETBOX_470_BETA1_COMPARISON_VERSION, NETBOX_470_BETA1_DISPLAY_VERSION
        ),
        VERSION=NETBOX_470_BETA1_DISPLAY_VERSION,
        PLUGINS_CONFIG={"netbox_proxbox": "not-a-mapping"},
    )
    registered = _install_fake_django(monkeypatch, settings)

    with caplog.at_level(logging.WARNING):
        register_netbox_compatibility_check(
            _FakeAppConfig(), logging.getLogger("test.compat")
        )

    assert len(caplog.records) == 1
    assert len(_run_registered_check(registered)) == 1


# ---------------------------------------------------------------------------
# The opt-out is W001-only and strictly boolean
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "truthy_but_not_true",
    ["false", "0", "no", "off", ["x"], {"a": 1}, 1, 2.5, object()],
)
def test_only_the_literal_boolean_true_silences_the_notice(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    truthy_but_not_true: object,
) -> None:
    """PLUGINS_CONFIG is often assembled from environment variables.

    There, the string "false" and the string "0" are both truthy in Python.
    Accepting anything truthy would silence the warning for an operator who
    wrote something that reads like a refusal — the exact opposite of the
    documented fail-open behaviour.
    """
    _reset_registration_guard(monkeypatch)
    settings = types.SimpleNamespace(
        RELEASE=_FakeRelease(
            NETBOX_470_BETA1_COMPARISON_VERSION, NETBOX_470_BETA1_DISPLAY_VERSION
        ),
        VERSION=NETBOX_470_BETA1_DISPLAY_VERSION,
        PLUGINS_CONFIG={"netbox_proxbox": {SILENCE_SETTING_NAME: truthy_but_not_true}},
    )
    registered = _install_fake_django(monkeypatch, settings)

    with caplog.at_level(logging.WARNING):
        register_netbox_compatibility_check(
            _FakeAppConfig(), logging.getLogger("test.compat")
        )

    assert len(caplog.records) == 1, f"{truthy_but_not_true!r} must not silence"
    assert len(_run_registered_check(registered)) == 1


def test_the_w001_opt_out_does_not_silence_w002(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Accepting "this release is experimental" is not accepting "we no longer know".

    W002 means the compatibility band could not be determined at all. An
    operator who opted out of the maturity notice has said nothing about that,
    and suppressing it would recreate exactly the silent-success state W002 was
    added to prevent.
    """
    _reset_registration_guard(monkeypatch)
    settings = types.SimpleNamespace(
        RELEASE=None,
        VERSION=None,  # detection fails -> W002 territory
        PLUGINS_CONFIG={"netbox_proxbox": {SILENCE_SETTING_NAME: True}},
    )
    registered = _install_fake_django(monkeypatch, settings)

    with caplog.at_level(logging.WARNING):
        register_netbox_compatibility_check(
            _FakeAppConfig(), logging.getLogger("test.compat")
        )

    results = _run_registered_check(registered)
    assert len(results) == 1 and results[0].id == "netbox_proxbox.W002"
    assert len(caplog.records) == 1


def test_w002_is_still_silenceable_by_naming_it_explicitly(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The escape hatch stays available — it just has to be deliberate."""
    _reset_registration_guard(monkeypatch)
    settings = types.SimpleNamespace(
        RELEASE=None,
        VERSION=None,
        SILENCED_SYSTEM_CHECKS=["netbox_proxbox.W002"],
    )
    registered = _install_fake_django(monkeypatch, settings)

    with caplog.at_level(logging.WARNING):
        register_netbox_compatibility_check(
            _FakeAppConfig(), logging.getLogger("test.compat")
        )

    assert _run_registered_check(registered) == []
    assert caplog.records == []
