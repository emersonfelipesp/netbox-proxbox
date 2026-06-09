"""Regression tests for multi-Proxmox-endpoint identity scoping.

These cover the endpoint-identity layer that keeps a second Proxmox endpoint
from being attributed the first endpoint's clusters/nodes/VMs:

- ``proxmox_backend_name`` embeds the NetBox pk as a stable ``(nb:<pk>)`` suffix.
- ``resolve_backend_endpoint_id`` / ``resolve_backend_endpoint_ids`` translate a
  plugin ``ProxmoxEndpoint`` to the backend's own autoincrement database id by
  matching that name, because plugin pk != backend id in general.
- Unregistered endpoints resolve to ``None`` (fail loud), never to a foreign id.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def _load_backend_sync_module(monkeypatch, *, endpoints_payload):
    """Load views/backend_sync.py with light stubs and a canned endpoint list."""
    pkg = types.ModuleType("netbox_proxbox")
    pkg.__path__ = [str(REPO_ROOT / "netbox_proxbox")]
    monkeypatch.setitem(sys.modules, "netbox_proxbox", pkg)

    views_pkg = types.ModuleType("netbox_proxbox.views")
    views_pkg.__path__ = [str(REPO_ROOT / "netbox_proxbox" / "views")]
    monkeypatch.setitem(sys.modules, "netbox_proxbox.views", views_pkg)

    models_mod = types.ModuleType("netbox_proxbox.models")
    models_mod.ProxmoxEndpoint = object
    monkeypatch.setitem(sys.modules, "netbox_proxbox.models", models_mod)

    utils_mod = types.ModuleType("netbox_proxbox.utils")
    utils_mod.get_ip_address_host = lambda value: (
        str(value).split("/")[0] if value else "127.0.0.1"
    )
    monkeypatch.setitem(sys.modules, "netbox_proxbox.utils", utils_mod)

    error_utils_mod = types.ModuleType("netbox_proxbox.views.error_utils")
    error_utils_mod.extract_backend_error_detail = lambda exc: (str(exc), None)
    error_utils_mod.parse_requests_response_json = lambda response, log_label=None: (
        response.json(),
        None,
    )
    monkeypatch.setitem(
        sys.modules, "netbox_proxbox.views.error_utils", error_utils_mod
    )

    spec = importlib.util.spec_from_file_location(
        "netbox_proxbox.views.backend_sync",
        REPO_ROOT / "netbox_proxbox" / "views" / "backend_sync.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "netbox_proxbox.views.backend_sync", module)
    spec.loader.exec_module(module)

    def _fake_get(url, headers=None, verify=True, timeout=15):
        assert url.endswith("/proxmox/endpoints")
        return _FakeResponse(endpoints_payload)

    monkeypatch.setattr(module.requests, "get", _fake_get)
    return module


def _endpoint(pk, name, *, enabled=True):
    return SimpleNamespace(pk=pk, name=name, enabled=enabled)


def test_proxmox_backend_name_embeds_plugin_pk(monkeypatch):
    backend_sync = _load_backend_sync_module(monkeypatch, endpoints_payload=[])
    assert backend_sync.proxmox_backend_name(_endpoint(3, "PVE")) == "PVE (nb:3)"


def test_resolve_backend_endpoint_id_matches_by_name(monkeypatch):
    """Plugin pk 3 must resolve to the backend's own id (7), matched by name."""
    backend_sync = _load_backend_sync_module(
        monkeypatch,
        endpoints_payload=[
            {"id": 5, "name": "Other (nb:1)"},
            {"id": 7, "name": "PVE (nb:3)"},
        ],
    )
    backend_id, error = backend_sync.resolve_backend_endpoint_id(
        _endpoint(3, "PVE"), base_url="http://backend:8000"
    )
    assert error is None
    assert backend_id == 7


def test_sync_proxmox_endpoint_to_backend_skips_disabled_without_http(monkeypatch):
    """A disabled endpoint must not be listed, created, or updated on proxbox-api."""
    backend_sync = _load_backend_sync_module(monkeypatch, endpoints_payload=[])
    monkeypatch.setattr(
        backend_sync.requests,
        "get",
        lambda *args, **kwargs: pytest.fail("disabled endpoint made backend GET"),
    )

    ok, detail, status = backend_sync.sync_proxmox_endpoint_to_backend(
        _endpoint(1, "Disabled PVE", enabled=False),
        base_url="http://backend:8000",
    )

    assert ok is False
    assert status is None
    assert "disabled" in detail


def test_resolve_backend_endpoint_id_skips_disabled_without_http(monkeypatch):
    """A disabled endpoint must not be resolved through the backend endpoint list."""
    backend_sync = _load_backend_sync_module(monkeypatch, endpoints_payload=[])
    monkeypatch.setattr(
        backend_sync.requests,
        "get",
        lambda *args, **kwargs: pytest.fail("disabled endpoint made backend GET"),
    )

    backend_id, detail = backend_sync.resolve_backend_endpoint_id(
        _endpoint(1, "Disabled PVE", enabled=False),
        base_url="http://backend:8000",
    )

    assert backend_id is None
    assert "disabled" in detail


def test_resolve_backend_endpoint_id_fails_loud_when_unregistered(monkeypatch):
    """An endpoint absent from the backend resolves to None, never a foreign id."""
    backend_sync = _load_backend_sync_module(
        monkeypatch,
        endpoints_payload=[{"id": 5, "name": "Other (nb:1)"}],
    )
    backend_id, error = backend_sync.resolve_backend_endpoint_id(
        _endpoint(3, "PVE"), base_url="http://backend:8000"
    )
    assert backend_id is None
    assert error is not None
    assert "PVE (nb:3)" in error


def test_resolve_backend_endpoint_ids_batches_and_omits_unmatched(monkeypatch):
    """Batch resolution maps matched pks and drops endpoints with no backend row."""
    backend_sync = _load_backend_sync_module(
        monkeypatch,
        endpoints_payload=[
            {"id": 11, "name": "A (nb:1)"},
            {"id": 22, "name": "B (nb:2)"},
        ],
    )
    mapping, error = backend_sync.resolve_backend_endpoint_ids(
        [_endpoint(1, "A"), _endpoint(2, "B"), _endpoint(3, "C")],
        base_url="http://backend:8000",
    )
    assert error is None
    assert mapping == {1: 11, 2: 22}
    assert 3 not in mapping


def test_resolve_backend_endpoint_id_propagates_list_error(monkeypatch):
    """A backend that returns a non-list payload yields an error, not a match."""
    backend_sync = _load_backend_sync_module(
        monkeypatch, endpoints_payload={"unexpected": "shape"}
    )
    backend_id, error = backend_sync.resolve_backend_endpoint_id(
        _endpoint(3, "PVE"), base_url="http://backend:8000"
    )
    assert backend_id is None
    assert error is not None
