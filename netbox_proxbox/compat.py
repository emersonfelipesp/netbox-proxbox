"""Shared NetBox version-compatibility policy for the Proxbox plugin stack.

**Vendored module.** Byte-identical copies live in every Proxbox-stack NetBox
plugin — ``netbox-proxbox``, ``netbox-ceph``, ``netbox-packer``,
``netbox-pbs``, and ``netbox-pdm``. It carries no plugin-specific literals on
purpose, so the five copies can be diffed for drift; the
``proxbox-stack-code-review`` skill carries that check. Changing it in one repo
means changing it in all five, and bumping :data:`CONTRACT_VERSION` when the
contract itself moves.

Two support tiers:

* **stable** — ``4.5.8`` through ``4.6.99``. Fully supported and CI-gated.
* **experimental** — the exact canonical ``4.7.0-beta2`` release identity. The
  plugin loads and runs normally, but this upstream pre-release is not yet
  certified for production, so a Django system check warns once at startup.

Stable admission is left to NetBox's stock
:class:`~netbox.plugins.PluginConfig` version gate. NetBox supplies only the
bare ``RELEASE.version`` to that gate, so a second fail-closed identity check
reads the canonical release metadata for the held 4.7 line. An exact beta2
identity produces a warning, never an error; an unreviewed 4.7 identity causes
NetBox to warn and omit this plugin while startup continues.

A note on beta version strings, because it is the whole reason the cap moved.
NetBox splits its release identity in ``release.yaml``: at tag
``v4.7.0-beta2`` the file reads ``version: "4.7.0"`` with
``designation: "beta2"``, and ``settings.py`` passes ``RELEASE.version`` — the
bare ``"4.7.0"`` — to the plugin gate. ``RELEASE.full_version`` carries the
human-facing ``"4.7.0-beta2"``. So the gate never sees the pre-release
qualifier, and a cap of ``"4.6.99"`` rejects the beta outright.
:func:`validate_held_netbox_release_identity` reads ``release.yaml`` directly
for exactly this reason. It never trusts ``load_release_data()`` because that
helper overlays local data; ``local/release.yaml`` may add only an informational
``build`` value while the canonical file alone supplies version and
designation.

**Import-time constraint.** NetBox calls ``PluginConfig.validate()`` while
``netbox/settings.py`` is still executing, and that import reaches this module.
Nothing here may read ``django.conf.settings`` — or import Django at all — at
module scope. Every Django touch lives inside a function.
"""

from __future__ import annotations

import logging
from enum import StrEnum
from typing import Any

from packaging import version as _version

__all__ = [
    "APPROVED_EXPERIMENTAL_NETBOX_DESIGNATION",
    "APPROVED_EXPERIMENTAL_NETBOX_VERSION",
    "CONTRACT_VERSION",
    "EXPERIMENTAL_MAX_NETBOX_VERSION",
    "EXPERIMENTAL_MIN_NETBOX_VERSION",
    "NetBoxSupportLevel",
    "PLUGIN_MAX_VERSION",
    "PLUGIN_MIN_VERSION",
    "STABLE_MAX_NETBOX_VERSION",
    "SILENCE_SETTING_NAME",
    "STABLE_MIN_NETBOX_VERSION",
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

#: Bumped whenever the shared contract below changes shape. All five vendored
#: copies must agree on this value; a mismatch means one repo was updated alone.
#:
#: v4 — also recognizes NetBox's documented full-version form when an allowed
#: local build suffix follows the canonical beta2 designation.
CONTRACT_VERSION = "netbox-compat-v4"

#: Oldest NetBox release the Proxbox stack supports at all.
STABLE_MIN_NETBOX_VERSION = "4.5.8"
#: Newest NetBox release covered by the certified, CI-gated stable tier.
STABLE_MAX_NETBOX_VERSION = "4.6.99"
#: First NetBox release admitted on an experimental basis.
EXPERIMENTAL_MIN_NETBOX_VERSION = "4.7.0"
#: Only bare 4.7 version admitted by NetBox's stock numeric gate.
EXPERIMENTAL_MAX_NETBOX_VERSION = "4.7.0"
#: Canonical release identity approved on the held 4.7 line.
APPROVED_EXPERIMENTAL_NETBOX_VERSION = "4.7.0"
APPROVED_EXPERIMENTAL_NETBOX_DESIGNATION = "beta2"

#: Consumed by each plugin's ``PluginConfig.min_version``.
PLUGIN_MIN_VERSION = STABLE_MIN_NETBOX_VERSION
#: Consumed by each plugin's ``PluginConfig.max_version``. This is the
#: experimental numeric ceiling. The identity guard below further narrows this
#: bare version to the exact canonical beta2 designation.
PLUGIN_MAX_VERSION = EXPERIMENTAL_MAX_NETBOX_VERSION

# Guards against a second ``register_netbox_compatibility_check`` call for the
# same app emitting the warning twice. ``ready()`` is normally called once, but
# test harnesses and ``manage.py`` re-entry can call it again, and a duplicated
# startup warning reads as two separate problems.
_REGISTERED_APP_LABELS: set[str] = set()

# How many trailing ``-segment`` groups is_prerelease_netbox() will peel off a
# display version before giving up. NetBox appends at most a designation and a
# build, and a build may itself contain dashes (``Docker-3.4.0``), so a small
# bound covers every real shape without looping on pathological input.
_VERSION_SUFFIX_STRIP_LIMIT = 6

#: Key an operator may set in a plugin's ``PLUGINS_CONFIG`` entry to silence
#: its maturity notice. See :func:`_check_is_silenced` for why this exists
#: despite the module otherwise adding no settings of its own.
SILENCE_SETTING_NAME = "silence_netbox_compatibility_warning"


def _loader_requires_identity_check(
    plugin_config: type[Any], netbox_version: str
) -> bool:
    """Return whether canonical metadata must be checked, failing closed."""
    approved_version = plugin_config.approved_netbox_version
    approved_designation = plugin_config.approved_netbox_designation
    approved_display_version = f"{approved_version}-{approved_designation}"
    candidate_text = netbox_version
    if netbox_version.startswith(f"{approved_display_version}-"):
        candidate_text = approved_display_version
    try:
        candidate = _version.parse(candidate_text)
        approved_numeric = _version.parse(approved_version)
        approved_prerelease = _version.parse(approved_display_version)
    except _version.InvalidVersion as error:
        if not netbox_version.startswith("4.7"):
            return False
        from core.exceptions import IncompatiblePluginError

        raise IncompatiblePluginError(
            f"Plugin {plugin_config.__module__} cannot verify malformed "
            f"NetBox 4.7 version {netbox_version!r}."
        ) from error

    on_held_numeric_line = candidate.release[:2] == approved_numeric.release[
        :2
    ] and not any(candidate.release[2:])
    if not on_held_numeric_line:
        return False
    if candidate in {approved_numeric, approved_prerelease}:
        return True

    from core.exceptions import IncompatiblePluginError

    raise IncompatiblePluginError(
        f"Plugin {plugin_config.__module__} is approved only for NetBox "
        f"{approved_version}-{plugin_config.approved_netbox_designation} "
        f"on the 4.7 line (loader: {netbox_version})."
    )


def _read_local_release_data(
    plugin_config: type[Any],
    release_base_path: Any,
    local_release_relative_path: Any,
    incompatible_error: type[Exception],
) -> object:
    """Read optional local metadata once and translate every read/parse failure."""
    import yaml

    try:
        local_release_text = release_base_path.joinpath(
            local_release_relative_path
        ).read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except Exception as error:
        raise incompatible_error(
            f"Plugin {plugin_config.__module__} could not verify "
            f"{local_release_relative_path}: {error}"
        ) from error

    try:
        local_release_data = yaml.safe_load(local_release_text)
    except Exception as error:
        raise incompatible_error(
            f"Plugin {plugin_config.__module__} could not verify "
            f"{local_release_relative_path}: {error}"
        ) from error
    return {} if local_release_data is None else local_release_data


def _validate_loader_build_suffix(
    plugin_config: type[Any],
    netbox_version: str,
    local_release_data: dict[str, object],
    incompatible_error: type[Exception],
) -> None:
    """Match an incoming full-version build suffix to the local snapshot."""
    approved_display_version = (
        f"{plugin_config.approved_netbox_version}-"
        f"{plugin_config.approved_netbox_designation}"
    )
    if not netbox_version.startswith(f"{approved_display_version}-"):
        return

    local_build = local_release_data.get("build")
    expected_display_version = approved_display_version
    if local_build:
        expected_display_version = f"{expected_display_version}-{local_build}"
    if netbox_version != expected_display_version:
        raise incompatible_error(
            f"Plugin {plugin_config.__module__} cannot match NetBox loader "
            f"version {netbox_version!r} to canonical/local release metadata "
            f"({expected_display_version})."
        )


def validate_held_netbox_release_identity(
    plugin_config: type[Any], netbox_version: str
) -> None:
    """Admit only canonical NetBox v4.7.0-beta2 on the held 4.7 line.

    NetBox's stock plugin gate passes only ``RELEASE.version`` (``4.7.0`` for
    beta2, later prereleases, and GA), so the numeric maximum cannot identify
    the reviewed release. Stable versions return immediately and retain stock
    :class:`PluginConfig` behavior. For 4.7.0, read the canonical and optional
    local release snapshots exactly once. Local metadata may add only ``build``;
    it can never replace the canonical version or designation.

    Source commit, Python archive, and dependency provenance remain CI/operator
    attestations. This runtime guard attests release identity only.
    """
    if not _loader_requires_identity_check(plugin_config, netbox_version):
        return

    approved_version = plugin_config.approved_netbox_version

    from pathlib import Path

    import yaml
    from core.exceptions import IncompatiblePluginError

    try:
        from utilities import release as netbox_release

        release_path = netbox_release.RELEASE_PATH
        local_release_relative_path = netbox_release.LOCAL_RELEASE_PATH
        release_base_path = Path(netbox_release._find_release_base_path())
    except Exception as error:
        raise IncompatiblePluginError(
            f"Plugin {plugin_config.__module__} could not locate canonical NetBox "
            f"release metadata: {error}"
        ) from error

    try:
        release_data = yaml.safe_load(
            release_base_path.joinpath(release_path).read_text(encoding="utf-8")
        )
    except Exception as error:
        raise IncompatiblePluginError(
            f"Plugin {plugin_config.__module__} could not verify canonical NetBox "
            f"release identity from {release_path}: {error}"
        ) from error
    if type(release_data) is not dict:
        raise IncompatiblePluginError(
            f"Plugin {plugin_config.__module__} requires a mapping in "
            f"{release_path} while NetBox 4.7 is release-held."
        )

    local_release_data = _read_local_release_data(
        plugin_config,
        release_base_path,
        local_release_relative_path,
        IncompatiblePluginError,
    )

    unexpected_keys = (
        set(local_release_data) - {"build"}
        if type(local_release_data) is dict
        else {"invalid-content"}
    )
    if unexpected_keys:
        unexpected_labels = ", ".join(sorted(map(str, unexpected_keys)))
        raise IncompatiblePluginError(
            f"Plugin {plugin_config.__module__} permits only the build key in "
            f"{local_release_relative_path} while NetBox 4.7 is release-held "
            f"(unexpected: {unexpected_labels})."
        )

    version = release_data.get("version")
    designation = release_data.get("designation")
    approved_designation = plugin_config.approved_netbox_designation
    if version != approved_version or designation != approved_designation:
        current_release = str(version)
        if designation:
            current_release = f"{current_release}-{designation}"
        raise IncompatiblePluginError(
            f"Plugin {plugin_config.__module__} is approved only for NetBox "
            f"{approved_version}-{approved_designation} on the 4.7 line "
            f"(canonical: {current_release})."
        )

    _validate_loader_build_suffix(
        plugin_config,
        netbox_version,
        local_release_data,
        IncompatiblePluginError,
    )


class NetBoxSupportLevel(StrEnum):
    """How the running NetBox release relates to the declared support bands.

    ``StrEnum`` rather than ``(str, Enum)``: every plugin in this family
    declares ``requires-python >= 3.12``, so it is always available, and some
    of the repos' lint configurations reject the older pairing.
    """

    #: Older than :data:`STABLE_MIN_NETBOX_VERSION`; the plugin refuses to load.
    UNSUPPORTED_OLD = "unsupported-old"
    #: Within the certified, CI-gated band. No warning.
    STABLE = "stable"
    #: Admitted, loads and runs, not yet certified. Warns once at startup.
    EXPERIMENTAL = "experimental"
    #: Newer than :data:`EXPERIMENTAL_MAX_NETBOX_VERSION`; refuses to load.
    UNSUPPORTED_NEW = "unsupported-new"


def netbox_support_level(netbox_version: str) -> NetBoxSupportLevel:
    """Classify ``netbox_version`` against the stable and experimental bands.

    Accepts either form of the NetBox release string — the bare ``"4.7.0"``
    that the plugin gate compares against, or the ``"4.7.0-beta2"`` display
    form — and classifies both as :attr:`NetBoxSupportLevel.EXPERIMENTAL`,
    since ``4.7.0b2`` also sorts above the stable ceiling.

    Raises:
        packaging.version.InvalidVersion: if the string is not a version at
            all. Callers that must not fail hard — the system check below — are
            responsible for catching it and reporting the failure to classify,
            rather than letting it reach startup.
    """
    parsed = _version.parse(str(netbox_version))

    if parsed < _version.parse(STABLE_MIN_NETBOX_VERSION):
        return NetBoxSupportLevel.UNSUPPORTED_OLD
    if parsed <= _version.parse(STABLE_MAX_NETBOX_VERSION):
        return NetBoxSupportLevel.STABLE
    if parsed <= _version.parse(EXPERIMENTAL_MAX_NETBOX_VERSION):
        return NetBoxSupportLevel.EXPERIMENTAL
    return NetBoxSupportLevel.UNSUPPORTED_NEW


def detect_netbox_version() -> tuple[str, str]:
    """Return ``(comparison_version, display_version)`` for the running NetBox.

    ``comparison_version`` is what NetBox itself feeds to the plugin version
    gate (``RELEASE.version`` — ``"4.7.0"`` on a beta). ``display_version`` is
    the operator-facing string (``RELEASE.full_version`` — ``"4.7.0-beta2"``).

    ``settings.RELEASE`` exists as far back as the oldest supported release, so
    the ``settings.VERSION`` fallback is belt-and-braces for an unexpected
    layout rather than a routine path.

    Raises:
        RuntimeError: if neither attribute yields a usable version string.
    """
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
    """Classify the running NetBox release. Thin wrapper for callers and tests."""
    comparison_version, _display_version = detect_netbox_version()
    return netbox_support_level(comparison_version)


def is_prerelease_netbox(display_version: str, designation: str | None = None) -> bool:
    """True when the running NetBox is a pre-release (beta, rc, alpha).

    ``designation`` is authoritative when supplied: NetBox leaves it unset on a
    stable release and sets it to ``"beta2"``/``"rc1"`` otherwise. Prefer it.

    The ``display_version`` fallback exists for callers that only have the
    string, and it must cope with **build metadata**. ``full_version`` is built
    as ``version[-designation][-build]``, so a Docker image reports
    ``"4.7.0-beta2-Docker-3.4.0"`` — which ``packaging`` rejects outright. A
    naive parse would then return False and silently drop the pre-release
    caveat on every containerised install, which is precisely the deployment
    most likely to be running a beta. So on a parse failure, trailing
    ``-segment`` groups are peeled off one at a time until something parses.

    Returns False rather than raising if nothing parses: this only decorates a
    warning, and a failure to classify maturity must not escalate.
    """
    if designation:
        return True

    text = str(display_version)
    # Bounded: each iteration removes one trailing "-segment".
    for _attempt in range(_VERSION_SUFFIX_STRIP_LIMIT):
        try:
            return bool(_version.parse(text).is_prerelease)
        except Exception:  # noqa: BLE001 — try the next-shorter prefix
            if "-" not in text:
                return False
            text = text.rsplit("-", 1)[0]
    return False


def detect_netbox_designation() -> str | None:
    """Return NetBox's release designation (``"beta2"``, ``"rc1"``) or ``None``.

    This is the *authoritative* maturity signal and the reason it exists as a
    separate reader: ``RELEASE.full_version`` is assembled as
    ``version[-designation][-build]``, so a Docker image reports something like
    ``"4.7.0-beta2-Docker-3.4.0"`` — which is not a parseable version at all.
    A stable release leaves ``designation`` unset.

    Returns ``None`` rather than raising if it cannot be read; the caller falls
    back to parsing the display string.
    """
    try:
        from django.conf import settings

        release: Any = getattr(settings, "RELEASE", None)
        designation = getattr(release, "designation", None)
        return str(designation) if designation else None
    except Exception:  # noqa: BLE001 — cosmetic classification only
        return None


def _check_is_silenced(app_label: str, check_id: str) -> bool:
    """True when the operator has asked for this maturity notice to be quiet.

    Two mechanisms are honoured, and the second is load-bearing rather than a
    nicety.

    ``SILENCED_SYSTEM_CHECKS`` is Django's own mechanism, consulted here as well
    as by the check framework so that the ``ready()`` log line — which the
    framework knows nothing about — is silenced by the same action. **But NetBox
    does not read it from ``configuration.py``**: ``settings.py`` imports an
    explicit list of roughly a hundred named settings via
    ``getattr(configuration, ...)`` and this is not one of them, so setting it
    there changes nothing. It takes effect only through NetBox's
    ``local_settings.py`` hatch, which upstream labels *unsupported*.

    The supported path is therefore this plugin's own ``PLUGINS_CONFIG`` entry,
    which NetBox unambiguously does import::

        PLUGINS_CONFIG = {
            "<plugin>": {"silence_netbox_compatibility_warning": True},
        }

    That is a setting, and this module otherwise deliberately adds none. The
    distinction that matters: the plugin **works** with zero configuration on
    every supported NetBox — nothing here is an opt-in to *function*. This key
    only quiets an advisory the operator has already read and accepted, which is
    the one thing they cannot otherwise turn off.

    Fails *open* — an unreadable or malformed setting still shows the notice,
    the safe direction for a maturity warning.
    """
    try:
        from django.conf import settings

        if check_id in set(getattr(settings, "SILENCED_SYSTEM_CHECKS", None) or ()):
            return True

        # The PLUGINS_CONFIG opt-out covers the *maturity notice* only. W002
        # means "the compatibility band could not be determined at all", which
        # is a different statement and the one this module exists to make
        # loudly: an operator who accepted "this release is experimental" has
        # not thereby accepted "we no longer know whether it is supported".
        # Silencing W002 requires naming it explicitly in
        # SILENCED_SYSTEM_CHECKS, handled above.
        if check_id != f"{app_label}.W001":
            return False

        plugins_config = getattr(settings, "PLUGINS_CONFIG", None) or {}
        entry = plugins_config.get(app_label) or {}
        value = entry.get(SILENCE_SETTING_NAME, False)
        # Strictly ``True`` — not merely truthy. PLUGINS_CONFIG is frequently
        # assembled from environment variables, where the string "false" and
        # the string "0" are both truthy in Python. Accepting them would
        # suppress the warning for an operator who wrote something that reads
        # like a refusal, which is the opposite of the documented fail-open
        # behaviour. Anything that is not the literal boolean shows the notice.
        return value is True
    except Exception:  # noqa: BLE001 — suppression must never break startup
        return False


def experimental_warning_hint(app_label: str, display_version: str) -> str:
    """Compose the operator-facing hint that accompanies the maturity notice.

    A NetBox **pre-release** gets different advice, and the difference is the
    point. On a stable-but-uncertified release, silencing the notice once the
    risk is accepted is an ordinary decision. On a beta or release candidate it
    is not: upstream does not support the release in production and guarantees
    no upgrade path to the final release, so the hint must not read as
    clearance — silencing changes nothing about either fact.
    """
    if is_prerelease_netbox(display_version, detect_netbox_designation()):
        return (
            "The plugin itself is operational on this release; this is a "
            "maturity notice, not a plugin fault. Do not treat it as clearance "
            "to run a NetBox pre-release in production — that restriction is "
            "upstream's, and silencing this notice does not lift it. On an "
            "evaluation install you can quiet it with "
            f"PLUGINS_CONFIG['{app_label}']['{SILENCE_SETTING_NAME}'] = True."
        )
    return (
        "The plugin is fully operational; this is a maturity notice, not a "
        "fault. Once the risk is accepted, quiet it with "
        f"PLUGINS_CONFIG['{app_label}']['{SILENCE_SETTING_NAME}'] = True "
        "(NetBox does not read SILENCED_SYSTEM_CHECKS from configuration.py)."
    )


def experimental_warning_message(
    plugin_label: str, display_version: str, designation: str | None = None
) -> str:
    """Compose the operator-facing experimental-support warning.

    A NetBox pre-release gets an extra sentence. Upstream does not support beta
    and release-candidate builds in production and does not guarantee an upgrade
    path from a pre-release to the eventual GA release, so an operator who reads
    only "experimental" could otherwise conclude that silencing the notice is
    the whole story — and end up on a database state that cannot be upgraded
    forward. That is a materially different risk from running an uncertified but
    stable release, so it is said out loud rather than left to the docs.
    """
    message = (
        f"{plugin_label} is running on NetBox {display_version}, which is "
        f"supported on an experimental basis only. Certified support covers "
        f"NetBox {STABLE_MIN_NETBOX_VERSION} through "
        f"{STABLE_MAX_NETBOX_VERSION}."
    )
    if is_prerelease_netbox(display_version, designation):
        message += (
            f" NetBox {display_version} is also an upstream pre-release: "
            f"upstream does not support pre-releases in production and does "
            f"not guarantee an upgrade path from a pre-release to the final "
            f"release. Use it for evaluation on disposable data only."
        )
    return message


def register_netbox_compatibility_check(
    app_config: Any,
    logger: logging.Logger | None = None,
) -> None:
    """Register the experimental-support system check for ``app_config``.

    Call once from the plugin's ``AppConfig.ready()``. Registers a Django
    system check that emits ``<app_label>.W001`` when the running NetBox sits
    in the experimental band, and logs the same message immediately so it also
    reaches operators who never run ``manage.py check``.

    Both surfaces are warnings. Neither can block startup — refusing an
    out-of-range NetBox stays the job of the stock ``PluginConfig`` gate, which
    already ran by the time ``ready()`` is called.

    A failure to *classify* the version is reported as ``<app_label>.W002``
    rather than swallowed: a compatibility check that silently evaluates to
    "fine" whenever it breaks is worse than no check.
    """
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
            _comparison_version, display_version = detect_netbox_version()
            level = current_netbox_support_level()
        except Exception as exc:  # noqa: BLE001 — reported, never raised at startup
            if _check_is_silenced(app_label, f"{app_label}.W002"):
                return []
            return [
                DjangoWarning(
                    f"{plugin_label} could not determine the running NetBox "
                    f"version, so its compatibility band was not verified.",
                    hint=f"Underlying error: {exc}",
                    id=f"{app_label}.W002",
                )
            ]

        if level is not NetBoxSupportLevel.EXPERIMENTAL:
            return []

        # Django's check framework only honours SILENCED_SYSTEM_CHECKS, so the
        # PLUGINS_CONFIG opt-out has to be applied here too — otherwise it would
        # silence the log line while leaving `manage.py check` noisy.
        if _check_is_silenced(app_label, f"{app_label}.W001"):
            return []

        return [
            DjangoWarning(
                experimental_warning_message(
                    plugin_label, display_version, detect_netbox_designation()
                ),
                hint=experimental_warning_hint(app_label, display_version),
                id=f"{app_label}.W001",
            )
        ]

    _netbox_compatibility_check.__name__ = f"{app_label}_netbox_compatibility_check"
    register_check(_netbox_compatibility_check)

    log = logger or logging.getLogger(app_label or __name__)
    try:
        _comparison_version, display_version = detect_netbox_version()
        level = current_netbox_support_level()
    except Exception as exc:  # noqa: BLE001 — never block startup on a version read
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
            experimental_warning_message(
                plugin_label, display_version, detect_netbox_designation()
            ),
        )
