"""Regression tests for canonical package layout and removed legacy modules."""

from __future__ import annotations

import importlib
from pathlib import Path
import sys
import types

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIRECTORY = REPO_ROOT / "netbox_proxbox"


def _import_plugin_package(
    monkeypatch: pytest.MonkeyPatch, dotted_name: str
) -> types.ModuleType:
    package = types.ModuleType("netbox_proxbox")
    package.__path__ = [str(PACKAGE_DIRECTORY)]
    monkeypatch.setitem(sys.modules, "netbox_proxbox", package)
    monkeypatch.delitem(sys.modules, dotted_name, raising=False)
    return importlib.import_module(dotted_name)


def test_dead_legacy_sync_services_are_not_exported_or_packaged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    services = _import_plugin_package(monkeypatch, "netbox_proxbox.services")
    service_names = ("sync_backup_routines", "sync_sdn")
    service_directory = Path(services.__file__).resolve().parent

    for name in service_names:
        assert name not in services.__all__
        assert not hasattr(services, name)
        assert not (service_directory / f"{name}.py").exists()


def test_utils_import_resolves_to_the_package_without_a_shadow_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    utils = _import_plugin_package(monkeypatch, "netbox_proxbox.utils")
    package_directory = Path(utils.__file__).resolve().parent.parent

    assert Path(utils.__file__).as_posix().endswith("utils/__init__.py")
    assert not (package_directory / "utils.py").exists()


# --- built-artifact inventory ---------------------------------------------------

import io  # noqa: E402
import tarfile  # noqa: E402
import zipfile  # noqa: E402

import yaml  # noqa: E402

from scripts import check_dist_inventory  # noqa: E402


def _wheel(tmp_path, members):
    path = tmp_path / "netbox_proxbox-0.0.0-py3-none-any.whl"
    with zipfile.ZipFile(path, "w") as wheel:
        for member in members:
            wheel.writestr(member, "")
    return path


def _sdist(tmp_path, members):
    path = tmp_path / "netbox_proxbox-0.0.0.tar.gz"
    with tarfile.open(path, "w:gz") as sdist:
        for member in members:
            info = tarfile.TarInfo(member)
            sdist.addfile(info, io.BytesIO(b""))
    return path


def test_dist_inventory_refuses_removed_modules(tmp_path):
    wheel = _wheel(
        tmp_path,
        ["netbox_proxbox/__init__.py", "netbox_proxbox/services/sync_sdn.py"],
    )
    sdist = _sdist(
        tmp_path,
        ["netbox_proxbox-0.0.0/netbox_proxbox/utils.py"],
    )

    assert check_dist_inventory.forbidden_members(
        check_dist_inventory.artifact_members(wheel)
    ) == ["netbox_proxbox/services/sync_sdn.py"]
    assert check_dist_inventory.forbidden_members(
        check_dist_inventory.artifact_members(sdist)
    ) == ["netbox_proxbox-0.0.0/netbox_proxbox/utils.py"]
    assert check_dist_inventory.main([str(wheel), str(sdist)]) == 1


def test_dist_inventory_accepts_a_clean_artifact(tmp_path):
    wheel = _wheel(
        tmp_path,
        ["netbox_proxbox/__init__.py", "netbox_proxbox/utils/__init__.py"],
    )

    assert check_dist_inventory.main([str(wheel)]) == 0


def test_dist_inventory_list_matches_the_source_layout_guard():
    """One list of removed modules, checked in the source tree and the artifact."""
    expected = {
        "netbox_proxbox/services/sync_backup_routines.py",
        "netbox_proxbox/services/sync_sdn.py",
        "netbox_proxbox/utils.py",
    }
    assert set(check_dist_inventory.REMOVED_MODULES) == expected


def test_ci_builds_run_the_dist_inventory_check():
    """Both package builds must refuse an artifact that ships a removed module."""
    for path in (
        REPO_ROOT / ".gitea" / "workflows" / "ci.yml",
        REPO_ROOT / ".github" / "workflows" / "ci.yml",
    ):
        workflow = yaml.safe_load(path.read_text())
        runs = [
            step.get("run", "")
            for job in workflow["jobs"].values()
            for step in job.get("steps", [])
        ]
        building = [run for run in runs if "-m build" in run]
        assert building, f"{path} has no build step"
        for run in building:
            build_at = run.index("-m build")
            check_at = run.index(
                "scripts/check_dist_inventory.py dist/*.whl dist/*.tar.gz"
            )
            assert build_at < check_at, f"{path}: inventory check must follow the build"
            assert "twine check" not in run or check_at < run.index("twine check")
