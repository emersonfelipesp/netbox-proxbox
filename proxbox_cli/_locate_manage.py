"""Resolve the NetBox ``manage.py`` and the interpreter that should run it.

Used by ``pxb sync run`` to invoke ``manage.py proxbox_sync`` as a subprocess
without the operator having to know where NetBox is installed.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import NamedTuple

NETBOX_PATH_ENV_VAR = "NETBOX_PATH"
DEFAULT_NETBOX_PATH = Path("/opt/netbox/manage.py")

NOT_FOUND_MESSAGE = (
    "could not find manage.py — set $NETBOX_PATH or run from inside the project tree"
)


class ManageLocation(NamedTuple):
    """Resolved ``manage.py`` and the interpreter to invoke it with."""

    manage_py: Path
    python: Path


class ManagePyNotFoundError(RuntimeError):
    """Raised when no ``manage.py`` could be located via any source."""


def _is_netbox_install(manage_py: Path) -> bool:
    """Return True when ``manage.py``'s siblings look like a NetBox install.

    The check resolves ``manage.py`` first so symlinks (e.g. ``/opt/netbox``
    pointing at a versioned dir) point at the real install. The heuristic
    accepts either ``netbox/settings.py`` containing the literal
    ``from netbox.plugins`` import or the presence of
    ``netbox/configuration_example.py`` — the latter ships with every
    NetBox release.
    """
    try:
        resolved = manage_py.resolve()
    except OSError:
        return False

    netbox_dir = resolved.parent / "netbox"
    if (netbox_dir / "configuration_example.py").exists():
        return True

    settings = netbox_dir / "settings.py"
    if not settings.exists():
        return False
    try:
        return "from netbox.plugins" in settings.read_text(
            encoding="utf-8", errors="replace"
        )
    except OSError:
        return False


def _resolve_interpreter(manage_py: Path) -> Path:
    """Prefer the venv shipped next to ``manage.py``; fall back to ``sys.executable``."""
    try:
        resolved_parent = manage_py.resolve().parent
    except OSError:
        resolved_parent = manage_py.parent

    venv_python = resolved_parent / "venv" / "bin" / "python"
    if venv_python.exists():
        return venv_python
    return Path(sys.executable)


def _candidate_from_path_like(value: str | Path) -> Path | None:
    """Accept either a directory containing ``manage.py`` or a direct file path."""
    p = Path(value).expanduser()
    if p.is_dir():
        candidate = p / "manage.py"
        return candidate if candidate.is_file() else None
    if p.is_file():
        return p
    return None


def locate_manage_py(
    *,
    override: Path | None = None,
    config_manage_py: str | None = None,
) -> ManageLocation:
    """Resolve ``manage.py`` via the documented chain.

    Resolution order:

    1. ``override`` (typically ``--netbox-path``)
    2. Walk up from ``Path.cwd()``, applying the NetBox heuristic at each
       ancestor; non-NetBox ``manage.py`` files are skipped so the walk
       continues past unrelated Django projects.
    3. ``$NETBOX_PATH`` environment variable (file or directory).
    4. :data:`DEFAULT_NETBOX_PATH` (``/opt/netbox/manage.py``).
    5. ``config_manage_py`` (from ``~/.config/proxbox-cli/config.json``).
    6. Otherwise raise :class:`ManagePyNotFoundError`.

    Sources other than the walk-up are accepted as-is (the operator made an
    explicit choice). Only the walk-up applies the NetBox heuristic, which
    protects against an unrelated Django project on a parent directory.
    """
    if override is not None:
        candidate = _candidate_from_path_like(override)
        if candidate is not None:
            return ManageLocation(candidate, _resolve_interpreter(candidate))

    try:
        start = Path.cwd().resolve()
    except OSError:
        start = None

    if start is not None:
        for ancestor in (start, *start.parents):
            candidate = ancestor / "manage.py"
            if candidate.is_file() and _is_netbox_install(candidate):
                return ManageLocation(candidate, _resolve_interpreter(candidate))

    env_value = os.environ.get(NETBOX_PATH_ENV_VAR, "").strip()
    if env_value:
        candidate = _candidate_from_path_like(env_value)
        if candidate is not None:
            return ManageLocation(candidate, _resolve_interpreter(candidate))

    if DEFAULT_NETBOX_PATH.is_file():
        return ManageLocation(
            DEFAULT_NETBOX_PATH, _resolve_interpreter(DEFAULT_NETBOX_PATH)
        )

    if config_manage_py:
        candidate = _candidate_from_path_like(config_manage_py)
        if candidate is not None:
            return ManageLocation(candidate, _resolve_interpreter(candidate))

    raise ManagePyNotFoundError(NOT_FOUND_MESSAGE)
