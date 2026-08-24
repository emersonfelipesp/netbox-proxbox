"""Load a Django-free plugin module by path, with its pure siblings available.

``netbox_proxbox.anonymize`` and ``netbox_proxbox.views.error_utils`` are both
importable without Django, and several suites load them directly so the mocked
test run does not have to boot NetBox. Both now import
``netbox_proxbox.redaction``, and a plain ``spec_from_file_location`` cannot
satisfy that: resolving ``netbox_proxbox.redaction`` executes the real package
``__init__``, which needs Django, and reaching ``error_utils`` additionally
executes ``netbox_proxbox.views.__init__``, which needs a great deal more.

Pre-seeding stub packages plus the path-loaded ``redaction`` module into
``sys.modules`` makes those imports resolve from the cache instead. Every loader
needs the same preparation, so it lives here rather than being copied into each
suite -- copies of this were how the thing these modules guard drifted in the
first place.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types

_ROOT = Path(__file__).resolve().parents[1]
_PACKAGE = _ROOT / "netbox_proxbox"


def _load_by_path(monkeypatch, dotted: str, path: Path):
    """Execute *path* as module *dotted*, registering it before execution.

    Registration goes through ``monkeypatch`` rather than assigning
    ``sys.modules`` directly, so the entry is removed when the test ends. A raw
    assignment leaked ``netbox_proxbox.redaction`` and
    ``netbox_proxbox.anonymize`` into every subsequent test in the session --
    the shape that produces a suite where a test passes only because an earlier
    one left the right object behind.
    """
    spec = importlib.util.spec_from_file_location(dotted, path)
    assert spec is not None and spec.loader is not None, dotted
    module = importlib.util.module_from_spec(spec)
    # Registered *before* exec so a self-referential import resolves.
    monkeypatch.setitem(sys.modules, dotted, module)
    spec.loader.exec_module(module)
    return module


def _stub_package(dotted: str, path: Path) -> types.ModuleType:
    package = types.ModuleType(dotted)
    package.__path__ = [str(path)]
    return package


def install_pure_package(monkeypatch) -> None:
    """Seed stub ``netbox_proxbox`` / ``.views`` packages and real ``redaction``.

    ``monkeypatch`` scopes the ``sys.modules`` entries to the test, so a suite
    that later wants the real package is not poisoned by this one.
    """
    monkeypatch.setitem(
        sys.modules, "netbox_proxbox", _stub_package("netbox_proxbox", _PACKAGE)
    )
    monkeypatch.setitem(
        sys.modules,
        "netbox_proxbox.views",
        _stub_package("netbox_proxbox.views", _PACKAGE / "views"),
    )
    _load_by_path(monkeypatch, "netbox_proxbox.redaction", _PACKAGE / "redaction.py")


def load_pure_module(monkeypatch, dotted: str, relative_path: str):
    """Load ``netbox_proxbox/<relative_path>`` as *dotted*, siblings seeded."""
    install_pure_package(monkeypatch)
    return _load_by_path(monkeypatch, dotted, _PACKAGE / relative_path)


def load_redaction(monkeypatch):
    """Return the shared vocabulary module."""
    install_pure_package(monkeypatch)
    return sys.modules["netbox_proxbox.redaction"]


def load_anonymize(monkeypatch):
    return load_pure_module(monkeypatch, "netbox_proxbox.anonymize", "anonymize.py")


def load_error_utils(monkeypatch):
    return load_pure_module(
        monkeypatch, "netbox_proxbox.views.error_utils", "views/error_utils.py"
    )
