"""Mutation-sensitive tests for the held NetBox 4.7 release identity."""

from __future__ import annotations

import importlib.util
import sys
import types
from collections import Counter
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def load_compat_module():
    """Load compat.py without importing the NetBox-dependent package root."""
    module_name = "netbox_release_identity_guard_under_test"
    spec = importlib.util.spec_from_file_location(
        module_name, ROOT / "netbox_proxbox/compat.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


validate_held_netbox_release_identity = (
    load_compat_module().validate_held_netbox_release_identity
)


class IncompatiblePluginError(Exception):
    """Test double for NetBox's plugin compatibility exception."""


class HeldPluginConfig:
    """Minimal config surface consumed by the shared identity guard."""

    approved_netbox_version = "4.7.0"
    approved_netbox_designation = "beta2"


def install_release_modules(
    monkeypatch: pytest.MonkeyPatch, release_base: Path
) -> types.ModuleType:
    """Install the NetBox modules imported lazily by the guard."""
    core = types.ModuleType("core")
    core_exceptions = types.ModuleType("core.exceptions")
    core_exceptions.IncompatiblePluginError = IncompatiblePluginError
    core.exceptions = core_exceptions

    utilities = types.ModuleType("utilities")
    utilities_release = types.ModuleType("utilities.release")
    utilities_release.RELEASE_PATH = "release.yaml"
    utilities_release.LOCAL_RELEASE_PATH = "local/release.yaml"
    utilities_release._find_release_base_path = lambda: release_base
    utilities.release = utilities_release

    for name, module in {
        "core": core,
        "core.exceptions": core_exceptions,
        "utilities": utilities,
        "utilities.release": utilities_release,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)
    return utilities_release


def write_release(
    release_base: Path,
    *,
    version: str = "4.7.0",
    designation: str | None = "beta2",
    local: object = None,
) -> None:
    release_data = {"version": version, "edition": "Community"}
    if designation is not None:
        release_data["designation"] = designation
    release_base.joinpath("release.yaml").write_text(
        yaml.safe_dump(release_data), encoding="utf-8"
    )
    if local is not None:
        local_path = release_base / "local/release.yaml"
        local_path.parent.mkdir()
        local_path.write_text(yaml.safe_dump(local), encoding="utf-8")


def test_exact_beta_with_build_overlay_reads_each_snapshot_once(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    write_release(tmp_path, local={"build": "Docker-ci"})
    install_release_modules(monkeypatch, tmp_path)
    original_read_text = Path.read_text
    reads: Counter[Path] = Counter()

    def counted_read_text(path: Path, *args, **kwargs) -> str:
        reads[path] += 1
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", counted_read_text)
    validate_held_netbox_release_identity(HeldPluginConfig, "4.7.0")

    assert reads[tmp_path / "release.yaml"] == 1
    assert reads[tmp_path / "local/release.yaml"] == 1


def test_exact_beta_without_local_overlay_is_accepted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    write_release(tmp_path)
    install_release_modules(monkeypatch, tmp_path)
    validate_held_netbox_release_identity(HeldPluginConfig, "4.7.0")


def test_build_appended_loader_version_is_admitted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    write_release(tmp_path, local={"build": "Docker-3.4.0"})
    install_release_modules(monkeypatch, tmp_path)

    validate_held_netbox_release_identity(HeldPluginConfig, "4.7.0-beta2-Docker-3.4.0")


def test_build_appended_loader_version_must_match_local_metadata(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    write_release(tmp_path, local={"build": "Docker-3.4.0"})
    install_release_modules(monkeypatch, tmp_path)

    with pytest.raises(IncompatiblePluginError, match="cannot match NetBox loader"):
        validate_held_netbox_release_identity(
            HeldPluginConfig, "4.7.0-beta2-Docker-3.4.1"
        )


@pytest.mark.parametrize("loader_version", ["4.7", "4.7.0", "4.7b2", "4.7.0-beta2"])
def test_equivalent_beta2_loader_versions_are_admitted(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    loader_version: str,
) -> None:
    write_release(tmp_path)
    install_release_modules(monkeypatch, tmp_path)

    validate_held_netbox_release_identity(HeldPluginConfig, loader_version)


@pytest.mark.parametrize(
    "loader_version",
    ["4.7b1", "4.7rc1", "4.7.dev1", "4.7.0-beta1", "4.7.0.post1"],
)
def test_conflicting_47_loader_identity_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    loader_version: str,
) -> None:
    write_release(tmp_path)
    install_release_modules(monkeypatch, tmp_path)

    with pytest.raises(IncompatiblePluginError, match="approved only"):
        validate_held_netbox_release_identity(HeldPluginConfig, loader_version)


@pytest.mark.parametrize("loader_version", ["4.7.0-beta2", "4.7.0b2", "4.7.0rc1"])
def test_prerelease_loader_versions_cannot_bypass_identity_validation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    loader_version: str,
) -> None:
    write_release(tmp_path, designation="beta1")
    install_release_modules(monkeypatch, tmp_path)

    with pytest.raises(IncompatiblePluginError, match="approved only"):
        validate_held_netbox_release_identity(HeldPluginConfig, loader_version)


def test_malformed_47_loader_version_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    core = types.ModuleType("core")
    core_exceptions = types.ModuleType("core.exceptions")
    core_exceptions.IncompatiblePluginError = IncompatiblePluginError
    core.exceptions = core_exceptions
    monkeypatch.setitem(sys.modules, "core", core)
    monkeypatch.setitem(sys.modules, "core.exceptions", core_exceptions)

    with pytest.raises(IncompatiblePluginError, match="malformed NetBox 4.7"):
        validate_held_netbox_release_identity(HeldPluginConfig, "4.7-not-a-version")


@pytest.mark.parametrize("designation", [None, "beta1", "beta3", "rc1"])
def test_unreviewed_47_designations_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    designation: str | None,
) -> None:
    write_release(tmp_path, designation=designation)
    install_release_modules(monkeypatch, tmp_path)

    with pytest.raises(IncompatiblePluginError, match="approved only"):
        validate_held_netbox_release_identity(HeldPluginConfig, "4.7.0")


@pytest.mark.parametrize(
    "local_release",
    [
        {"version": "4.7.0", "designation": "beta2"},
        {"build": "Docker-ci", "designation": "beta2"},
        ["build", "Docker-ci"],
    ],
)
def test_local_release_identity_spoofing_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    local_release: object,
) -> None:
    write_release(tmp_path, local=local_release)
    install_release_modules(monkeypatch, tmp_path)

    with pytest.raises(IncompatiblePluginError, match="permits only the build key"):
        validate_held_netbox_release_identity(HeldPluginConfig, "4.7.0")


@pytest.mark.parametrize("contents", ["[not, a, mapping]", "version: [unterminated"])
def test_invalid_canonical_release_data_is_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, contents: str
) -> None:
    tmp_path.joinpath("release.yaml").write_text(contents, encoding="utf-8")
    install_release_modules(monkeypatch, tmp_path)

    with pytest.raises(IncompatiblePluginError, match="release.yaml"):
        validate_held_netbox_release_identity(HeldPluginConfig, "4.7.0")


@pytest.mark.parametrize("target", ["canonical", "local"])
def test_unreadable_release_data_is_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, target: str
) -> None:
    write_release(tmp_path, local={"build": "Docker-ci"})
    install_release_modules(monkeypatch, tmp_path)
    original_read_text = Path.read_text
    denied_path = tmp_path / (
        "release.yaml" if target == "canonical" else "local/release.yaml"
    )

    def fail_selected(path: Path, *args, **kwargs) -> str:
        if path == denied_path:
            raise PermissionError("denied")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fail_selected)
    with pytest.raises(IncompatiblePluginError, match="could not verify"):
        validate_held_netbox_release_identity(HeldPluginConfig, "4.7.0")


def test_release_locator_failure_is_translated_to_plugin_omission(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    release_module = install_release_modules(monkeypatch, tmp_path)

    def fail_locator() -> Path:
        raise RuntimeError("locator changed")

    monkeypatch.setattr(release_module, "_find_release_base_path", fail_locator)
    with pytest.raises(IncompatiblePluginError, match="could not locate"):
        validate_held_netbox_release_identity(HeldPluginConfig, "4.7.0")


def test_release_helper_import_failure_is_translated_to_plugin_omission(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    install_release_modules(monkeypatch, tmp_path)
    utilities_module = sys.modules["utilities"]
    monkeypatch.delattr(utilities_module, "release")
    monkeypatch.delitem(sys.modules, "utilities.release")

    with pytest.raises(IncompatiblePluginError, match="could not locate"):
        validate_held_netbox_release_identity(HeldPluginConfig, "4.7.0")


def test_malformed_local_release_data_is_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    write_release(tmp_path, local={"build": "Docker-ci"})
    tmp_path.joinpath("local/release.yaml").write_text(
        "build: [unterminated", encoding="utf-8"
    )
    install_release_modules(monkeypatch, tmp_path)

    with pytest.raises(
        IncompatiblePluginError, match="could not verify local/release.yaml"
    ):
        validate_held_netbox_release_identity(HeldPluginConfig, "4.7.0")


def test_stable_release_does_not_touch_47_release_helpers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delitem(sys.modules, "core", raising=False)
    monkeypatch.delitem(sys.modules, "core.exceptions", raising=False)
    monkeypatch.delitem(sys.modules, "utilities", raising=False)
    monkeypatch.delitem(sys.modules, "utilities.release", raising=False)

    validate_held_netbox_release_identity(HeldPluginConfig, "4.6.6")
