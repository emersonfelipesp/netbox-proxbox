"""Shared backward-compatible NetBox version policy for the Proxbox stack.

This module is vendored byte-for-byte in ``netbox-proxbox``, ``netbox-ceph``,
``netbox-packer``, ``netbox-pbs``, and ``netbox-pdm``. Keep the five copies
identical. The Emerson-owned stack retains its NetBox 4.5.8 floor while adding
support for the whole NetBox 4.7 series (through 4.7.99), so existing
installations can upgrade NetBox patch releases without changing plugin
configuration or database state.

NetBox imports this module while its settings are still loading. It therefore
must not import Django or read settings at module scope.
"""

from __future__ import annotations

import logging
from enum import StrEnum
from typing import Any

from packaging import version as _version

__all__ = [
    "CONTRACT_VERSION",
    "NetBoxSupportLevel",
    "PLUGIN_MAX_VERSION",
    "PLUGIN_MIN_VERSION",
    "STABLE_MAX_NETBOX_VERSION",
    "STABLE_MIN_NETBOX_VERSION",
    "SILENCE_SETTING_NAME",
    "current_netbox_support_level",
    "detect_netbox_designation",
    "detect_netbox_version",
    "experimental_warning_hint",
    "experimental_warning_message",
    "is_prerelease_netbox",
    "netbox_support_level",
    "register_netbox_compatibility_check",
    "validate_held_netbox_release_identity",
]

CONTRACT_VERSION = "netbox-compat-v5"
STABLE_MIN_NETBOX_VERSION = "4.5.8"
STABLE_MAX_NETBOX_VERSION = "4.7.99"
PLUGIN_MIN_VERSION = STABLE_MIN_NETBOX_VERSION
PLUGIN_MAX_VERSION = STABLE_MAX_NETBOX_VERSION
SILENCE_SETTING_NAME = "silence_netbox_compatibility_warning"
_REGISTERED_APP_LABELS: set[str] = set()
_VERSION_SUFFIX_STRIP_LIMIT = 6


class NetBoxSupportLevel(StrEnum):
    """Classification used by the advisory system check."""

    UNSUPPORTED_OLD = "unsupported-old"
    STABLE = "stable"
    EXPERIMENTAL = "experimental"
    UNSUPPORTED_NEW = "unsupported-new"


def netbox_support_level(netbox_version: str) -> NetBoxSupportLevel:
    """Classify a NetBox version against the stable and pre-release bands."""
    parsed = _version.parse(str(netbox_version))
    if parsed < _version.parse(STABLE_MIN_NETBOX_VERSION):
        return NetBoxSupportLevel.UNSUPPORTED_OLD
    if parsed <= _version.parse(STABLE_MAX_NETBOX_VERSION):
        if parsed.is_prerelease:
            return NetBoxSupportLevel.EXPERIMENTAL
        return NetBoxSupportLevel.STABLE
    return NetBoxSupportLevel.UNSUPPORTED_NEW


def detect_netbox_version() -> tuple[str, str]:
    """Return the loader comparison version and operator display version."""
    from django.conf import settings

    release: Any = getattr(settings, "RELEASE", None)
    comparison = getattr(release, "version", None)
    display = getattr(release, "full_version", None)
    if not comparison:
        fallback = getattr(settings, "VERSION", None)
        if not fallback:
            raise RuntimeError(
                "Unable to determine the running NetBox version: neither "
                "settings.RELEASE.version nor settings.VERSION is set."
            )
        comparison = str(fallback)
    return str(comparison), str(display or comparison)


def current_netbox_support_level() -> NetBoxSupportLevel:
    """Classify the running NetBox release."""
    comparison_version, display_version = detect_netbox_version()
    level = netbox_support_level(comparison_version)
    designation = detect_netbox_designation()
    if level is NetBoxSupportLevel.STABLE and is_prerelease_netbox(
        display_version, designation
    ):
        return NetBoxSupportLevel.EXPERIMENTAL
    return level


def is_prerelease_netbox(display_version: str, designation: str | None = None) -> bool:
    """Return whether a display version or authoritative designation is pre-release."""
    if designation:
        return True
    text = str(display_version)
    for _attempt in range(_VERSION_SUFFIX_STRIP_LIMIT):
        try:
            return bool(_version.parse(text).is_prerelease)
        except Exception:  # noqa: BLE001 — classification is advisory only
            if "-" not in text:
                return False
            text = text.rsplit("-", 1)[0]
    return False


def detect_netbox_designation() -> str | None:
    """Return NetBox's authoritative release designation, when available."""
    try:
        from django.conf import settings

        release: Any = getattr(settings, "RELEASE", None)
        designation = getattr(release, "designation", None)
        return str(designation) if designation else None
    except Exception:  # noqa: BLE001 — cosmetic classification only
        return None


def _classify_running_netbox() -> tuple[NetBoxSupportLevel, str, str | None]:
    """Return the running release's support level and display metadata."""
    _comparison_version, display_version = detect_netbox_version()
    level = current_netbox_support_level()
    designation = detect_netbox_designation()
    return level, display_version, designation


def _check_is_silenced(app_label: str, check_id: str) -> bool:
    """Return whether the operator explicitly silenced this advisory check."""
    try:
        from django.conf import settings

        if check_id in set(getattr(settings, "SILENCED_SYSTEM_CHECKS", None) or ()):
            return True
        if check_id != f"{app_label}.W001":
            return False
        plugins_config = getattr(settings, "PLUGINS_CONFIG", None) or {}
        entry = plugins_config.get(app_label) or {}
        return entry.get(SILENCE_SETTING_NAME, False) is True
    except Exception:  # noqa: BLE001 — suppression must never break startup
        return False


def experimental_warning_hint(app_label: str, display_version: str) -> str:
    """Compose the operator-facing hint for a pre-release advisory."""
    return (
        "The plugin itself is operational on this release; this is a maturity "
        "notice, not a plugin fault. Do not treat it as clearance to run a "
        "NetBox pre-release in production — silencing this notice does not lift "
        "that restriction. On an evaluation install you can quiet it with "
        f"PLUGINS_CONFIG['{app_label}']['{SILENCE_SETTING_NAME}'] = True."
    )


def experimental_warning_message(
    plugin_label: str, display_version: str, designation: str | None = None
) -> str:
    """Compose the operator-facing experimental-support warning."""
    message = (
        f"{plugin_label} is running on NetBox {display_version}, which is "
        "supported on an experimental basis only. Certified support covers "
        f"NetBox {STABLE_MIN_NETBOX_VERSION} through {STABLE_MAX_NETBOX_VERSION}."
    )
    if is_prerelease_netbox(display_version, designation):
        message += (
            f" NetBox {display_version} is also an upstream pre-release: "
            "upstream does not support pre-releases in production and does not "
            "guarantee an upgrade path from a pre-release to the final release. "
            "Use it for evaluation on disposable data only."
        )
    return message


def register_netbox_compatibility_check(
    app_config: Any,
    logger: logging.Logger | None = None,
) -> None:
    """Register one advisory check for pre-release NetBox versions."""
    from django.core.checks import Warning as DjangoWarning
    from django.core.checks import register as register_check

    app_label = str(getattr(app_config, "label", "") or getattr(app_config, "name", ""))
    plugin_label = str(getattr(app_config, "verbose_name", "") or app_label)
    if app_label in _REGISTERED_APP_LABELS:
        return
    _REGISTERED_APP_LABELS.add(app_label)

    def _netbox_compatibility_check(
        app_configs: Any = None, **kwargs: Any
    ) -> list[Any]:
        try:
            level, display_version, designation = _classify_running_netbox()
        except Exception as exc:  # noqa: BLE001 — report classification failure
            if _check_is_silenced(app_label, f"{app_label}.W002"):
                return []
            return [
                DjangoWarning(
                    f"{plugin_label} could not determine the running NetBox version, "
                    "so its compatibility band was not verified.",
                    hint=f"Underlying error: {exc}",
                    id=f"{app_label}.W002",
                )
            ]
        if level is not NetBoxSupportLevel.EXPERIMENTAL:
            return []
        if _check_is_silenced(app_label, f"{app_label}.W001"):
            return []
        return [
            DjangoWarning(
                experimental_warning_message(
                    plugin_label, display_version, designation
                ),
                hint=experimental_warning_hint(app_label, display_version),
                id=f"{app_label}.W001",
            )
        ]

    _netbox_compatibility_check.__name__ = f"{app_label}_netbox_compatibility_check"
    register_check(_netbox_compatibility_check)
    log = logger or logging.getLogger(app_label or __name__)
    try:
        level, display_version, designation = _classify_running_netbox()
    except Exception as exc:  # noqa: BLE001 — advisory logging never blocks startup
        if not _check_is_silenced(app_label, f"{app_label}.W002"):
            log.warning(
                "%s could not determine the running NetBox version (%s); "
                "compatibility band not verified.",
                plugin_label,
                exc,
            )
        return
    if level is NetBoxSupportLevel.EXPERIMENTAL and not _check_is_silenced(
        app_label, f"{app_label}.W001"
    ):
        log.warning(
            "%s",
            experimental_warning_message(plugin_label, display_version, designation),
        )


def validate_held_netbox_release_identity(
    plugin_config: type[Any], netbox_version: str
) -> None:
    """Retain the old hook as a no-op for callers from pre-GA plugin versions.

    Release identity is now verified by the exact CI source and package
    provenance. Runtime compatibility uses the stock numeric gate across the
    stable 4.5.8–4.7.99 range and performs no release-metadata reads.
    """
