"""Tests for proxbox_cli._locate_manage."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# proxbox_cli/__init__.py imports click and typer at module import time, so the
# test environment must have the CLI extras installed before any submodule of
# proxbox_cli can be imported — even one (like _locate_manage) that itself
# depends only on stdlib.
for module_name in ("click", "typer", "rich"):
    pytest.importorskip(module_name)

from proxbox_cli import _locate_manage  # noqa: E402 — guarded by importorskip above
from proxbox_cli._locate_manage import (  # noqa: E402 — guarded by importorskip above
    ManageLocation,
    ManagePyNotFoundError,
    NETBOX_PATH_ENV_VAR,
    locate_manage_py,
)


def _make_netbox_install(root: Path) -> Path:
    """Create a fake NetBox install at ``root``; return the manage.py path."""
    manage_py = root / "manage.py"
    manage_py.write_text("#!/usr/bin/env python\n")
    netbox_dir = root / "netbox"
    netbox_dir.mkdir()
    (netbox_dir / "configuration_example.py").write_text("# example config\n")
    return manage_py


def _make_django_only_install(root: Path) -> Path:
    """Create a non-NetBox Django project at ``root``; return the manage.py path."""
    manage_py = root / "manage.py"
    manage_py.write_text("#!/usr/bin/env python\n")
    (root / "settings.py").write_text("INSTALLED_APPS = []\n")
    return manage_py


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every test start with no NETBOX_PATH and a guaranteed-missing default."""
    monkeypatch.delenv(NETBOX_PATH_ENV_VAR, raising=False)
    monkeypatch.setattr(
        _locate_manage, "DEFAULT_NETBOX_PATH", Path("/nonexistent-default")
    )


def test_override_file(tmp_path: Path) -> None:
    manage_py = _make_netbox_install(tmp_path)
    location = locate_manage_py(override=manage_py)
    assert location.manage_py == manage_py


def test_override_directory(tmp_path: Path) -> None:
    manage_py = _make_netbox_install(tmp_path)
    location = locate_manage_py(override=tmp_path)
    assert location.manage_py == manage_py


def test_walk_up_finds_valid(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manage_py = _make_netbox_install(tmp_path)
    deep = tmp_path / "netbox" / "deep" / "nested"
    deep.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(deep)
    location = locate_manage_py()
    assert location.manage_py == manage_py


def test_walk_up_skips_invalid_continues(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root"
    mid = root / "mid"
    leaf = mid / "leaf"
    leaf.mkdir(parents=True)

    _make_netbox_install(root)
    _make_django_only_install(mid)

    monkeypatch.chdir(leaf)
    location = locate_manage_py()
    assert location.manage_py == root / "manage.py"


def test_walk_up_hits_filesystem_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.chdir(empty)
    with pytest.raises(ManagePyNotFoundError) as exc:
        locate_manage_py()
    assert NETBOX_PATH_ENV_VAR in str(exc.value)


def test_env_var_as_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manage_py = _make_netbox_install(tmp_path)
    empty = tmp_path.parent / f"empty-{tmp_path.name}"
    empty.mkdir(exist_ok=True)
    monkeypatch.chdir(empty)
    monkeypatch.setenv(NETBOX_PATH_ENV_VAR, str(tmp_path))
    location = locate_manage_py()
    assert location.manage_py == manage_py


def test_env_var_as_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manage_py = _make_netbox_install(tmp_path)
    empty = tmp_path.parent / f"empty-file-{tmp_path.name}"
    empty.mkdir(exist_ok=True)
    monkeypatch.chdir(empty)
    monkeypatch.setenv(NETBOX_PATH_ENV_VAR, str(manage_py))
    location = locate_manage_py()
    assert location.manage_py == manage_py


def test_env_var_nonexistent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.chdir(empty)
    monkeypatch.setenv(NETBOX_PATH_ENV_VAR, str(tmp_path / "does-not-exist"))
    with pytest.raises(ManagePyNotFoundError):
        locate_manage_py()


def test_default_path_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manage_py = _make_netbox_install(tmp_path)
    monkeypatch.setattr(_locate_manage, "DEFAULT_NETBOX_PATH", manage_py)
    empty = tmp_path.parent / f"empty-default-{tmp_path.name}"
    empty.mkdir(exist_ok=True)
    monkeypatch.chdir(empty)
    location = locate_manage_py()
    assert location.manage_py == manage_py


def test_config_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manage_py = _make_netbox_install(tmp_path)
    empty = tmp_path.parent / f"empty-cfg-{tmp_path.name}"
    empty.mkdir(exist_ok=True)
    monkeypatch.chdir(empty)
    location = locate_manage_py(config_manage_py=str(manage_py))
    assert location.manage_py == manage_py


def test_all_exhausted_raises_actionable_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.chdir(empty)
    with pytest.raises(ManagePyNotFoundError) as exc:
        locate_manage_py()
    msg = str(exc.value)
    assert NETBOX_PATH_ENV_VAR in msg
    assert "manage.py" in msg


def test_interpreter_prefers_venv(tmp_path: Path) -> None:
    manage_py = _make_netbox_install(tmp_path)
    venv_bin = tmp_path / "venv" / "bin"
    venv_bin.mkdir(parents=True)
    venv_python = venv_bin / "python"
    venv_python.write_text("#!/bin/sh\n")
    location = locate_manage_py(override=manage_py)
    assert location.python == venv_python


def test_interpreter_falls_back_to_sys_executable(tmp_path: Path) -> None:
    manage_py = _make_netbox_install(tmp_path)
    location = locate_manage_py(override=manage_py)
    assert location.python == Path(sys.executable)


def test_netbox_heuristic_via_settings_import(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    manage_py = root / "manage.py"
    manage_py.write_text("#!/usr/bin/env python\n")
    netbox_dir = root / "netbox"
    netbox_dir.mkdir()
    (netbox_dir / "settings.py").write_text(
        "from netbox.plugins import PluginConfig\nINSTALLED_APPS = ['core', 'dcim']\n"
    )
    # No configuration_example.py here — the import-substring branch must
    # carry this on its own.
    monkeypatch.chdir(root)
    location = locate_manage_py()
    assert location.manage_py == manage_py


def test_netbox_heuristic_via_configuration_example(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    manage_py = root / "manage.py"
    manage_py.write_text("#!/usr/bin/env python\n")
    netbox_dir = root / "netbox"
    netbox_dir.mkdir()
    (netbox_dir / "configuration_example.py").write_text("# placeholder\n")
    # Deliberately no settings.py — the configuration_example.py branch
    # must carry this on its own.
    monkeypatch.chdir(root)
    location = locate_manage_py()
    assert location.manage_py == manage_py


def test_non_netbox_manage_py_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _make_django_only_install(tmp_path)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ManagePyNotFoundError):
        locate_manage_py()


def test_namedtuple_shape(tmp_path: Path) -> None:
    manage_py = _make_netbox_install(tmp_path)
    location = locate_manage_py(override=manage_py)
    assert isinstance(location, ManageLocation)
    assert location.manage_py == manage_py
    assert isinstance(location.python, Path)
