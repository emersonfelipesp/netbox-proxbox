"""Behavior tests for ``services.endpoint_scope.enabled_backend_endpoint_scope``.

Pins the ``endpoint_ids`` narrowing contract added for the firewall/datacenter
pre-SSE passes: ``None`` keeps the historic all-enabled scope, a **non-empty**
list narrows the ORM filter to those plugin pks, and an **empty** list is a
resolved selection that matched nothing — it must produce *no scope at all*,
never fall through to "all". The backend reads a missing
``proxmox_endpoint_ids`` as "use every endpoint I hold", so silently widening
an empty selection would send the widest request the API accepts precisely when
the caller asked for the narrowest.

The module is loaded by file path against stub ``netbox_proxbox.models`` /
``views.backend_sync`` modules, so no NetBox bootstrap and no HTTP happen here.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_endpoint_scope_module(monkeypatch, *, rows, mapping=None, resolve_error=None):
    """Load the real ``endpoint_scope.py`` with a capturing manager and resolver."""
    calls = {"filter": [], "resolve": []}

    class _Manager:
        def filter(self, **kwargs):
            calls["filter"].append(kwargs)
            requested = kwargs.get("pk__in")
            if requested is None:
                return [row for row in rows if row.enabled]
            return [row for row in rows if row.enabled and row.pk in requested]

    models_mod = types.ModuleType("netbox_proxbox.models")
    models_mod.ProxmoxEndpoint = SimpleNamespace(objects=_Manager())
    monkeypatch.setitem(sys.modules, "netbox_proxbox.models", models_mod)

    views_pkg = types.ModuleType("netbox_proxbox.views")
    monkeypatch.setitem(sys.modules, "netbox_proxbox.views", views_pkg)
    backend_sync_mod = types.ModuleType("netbox_proxbox.views.backend_sync")

    def _resolve(endpoints, **kwargs):
        calls["resolve"].append([endpoint.pk for endpoint in endpoints])
        if resolve_error is not None:
            return {}, resolve_error
        resolved = (
            mapping if mapping is not None else {row.pk: row.pk * 10 for row in rows}
        )
        return {
            pk: resolved[pk] for pk in resolved if pk in {e.pk for e in endpoints}
        }, None

    backend_sync_mod.resolve_backend_endpoint_ids = _resolve
    monkeypatch.setitem(
        sys.modules, "netbox_proxbox.views.backend_sync", backend_sync_mod
    )

    pkg = types.ModuleType("netbox_proxbox")
    pkg.__path__ = [str(REPO_ROOT / "netbox_proxbox")]
    monkeypatch.setitem(sys.modules, "netbox_proxbox", pkg)
    services_pkg = types.ModuleType("netbox_proxbox.services")
    services_pkg.__path__ = [str(REPO_ROOT / "netbox_proxbox" / "services")]
    monkeypatch.setitem(sys.modules, "netbox_proxbox.services", services_pkg)

    sys.modules.pop("netbox_proxbox.services.endpoint_scope", None)
    spec = importlib.util.spec_from_file_location(
        "netbox_proxbox.services.endpoint_scope",
        REPO_ROOT / "netbox_proxbox" / "services" / "endpoint_scope.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "netbox_proxbox.services.endpoint_scope", module)
    spec.loader.exec_module(module)
    module._calls = calls
    return module


def _rows():
    return [
        SimpleNamespace(pk=1, enabled=True),
        SimpleNamespace(pk=2, enabled=True),
        SimpleNamespace(pk=3, enabled=False),
    ]


def test_no_selection_keeps_the_all_enabled_scope(monkeypatch):
    """``endpoint_ids=None`` is "no selection to honour" — the historic scope."""
    module = _load_endpoint_scope_module(monkeypatch, rows=_rows())

    params, mapping, error = module.enabled_backend_endpoint_scope(
        base_url="http://backend:8000"
    )

    assert error is None
    assert params == {"source": "database", "proxmox_endpoint_ids": "10,20"}
    assert mapping == {1: 10, 2: 20}
    assert module._calls["filter"] == [{"enabled": True}], (
        "no selection must not add a pk filter"
    )


def test_a_selection_narrows_the_orm_filter_to_those_pks(monkeypatch):
    """A non-empty selection reaches the ORM as ``pk__in`` beside ``enabled``."""
    module = _load_endpoint_scope_module(monkeypatch, rows=_rows())

    params, mapping, error = module.enabled_backend_endpoint_scope(
        base_url="http://backend:8000", endpoint_ids=[2, 3]
    )

    assert error is None
    assert module._calls["filter"] == [{"enabled": True, "pk__in": [2, 3]}]
    # pk 3 is disabled, so only pk 2 survives the filter and reaches the wire.
    assert params == {"source": "database", "proxmox_endpoint_ids": "20"}
    assert mapping == {2: 20}
    assert module._calls["resolve"] == [[2]], (
        "only the endpoints in scope may be resolved to backend ids"
    )


def test_an_empty_selection_is_no_scope_never_all(monkeypatch):
    """``[]`` resolved to nothing must return before the ORM and the backend.

    Falling through would build the all-enabled scope — the widest request the
    backend accepts — exactly when the caller asked for the narrowest.
    """
    module = _load_endpoint_scope_module(monkeypatch, rows=_rows())

    params, mapping, error = module.enabled_backend_endpoint_scope(
        base_url="http://backend:8000", endpoint_ids=[]
    )

    assert (params, mapping, error) == (None, {}, None)
    assert module._calls["filter"] == [], "the ORM must not be consulted"
    assert module._calls["resolve"] == [], "the backend must not be consulted"


def test_a_selection_matching_no_enabled_endpoint_is_no_scope(monkeypatch):
    """A selection whose every pk is disabled or gone also yields no scope."""
    module = _load_endpoint_scope_module(monkeypatch, rows=_rows())

    params, mapping, error = module.enabled_backend_endpoint_scope(
        base_url="http://backend:8000", endpoint_ids=[3, 99]
    )

    assert (params, mapping, error) == (None, {}, None)
    assert module._calls["resolve"] == [], "nothing in scope means nothing to resolve"
