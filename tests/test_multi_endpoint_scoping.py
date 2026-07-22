"""Regression tests for multi-Proxmox-endpoint identity scoping.

These cover the endpoint-identity layer that keeps a second Proxmox endpoint
from being attributed the first endpoint's clusters/nodes/VMs:

- ``proxmox_backend_name`` embeds the NetBox pk as a stable ``(nb:<pk>)`` suffix.
- ``resolve_backend_endpoint_id`` / ``resolve_backend_endpoint_ids`` translate a
  plugin ``ProxmoxEndpoint`` to the backend's own autoincrement database id by
  locating that name, because plugin pk != backend id in general.
- The located row is then **confirmed** to still dial the same Proxmox host.
  The name says *which* row is ours; it says nothing about whether the row is
  still fresh. The endpoint push happens in the sync preflight where a failure
  is only warned about, so a retargeted endpoint whose push failed leaves the
  backend holding the *previous* host under our name — and syncing through that
  id would reflect the old host's inventory into NetBox under the new endpoint.
- Unregistered endpoints resolve to ``None`` (fail loud), never to a foreign id.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.django_stubs import install_django_stubs


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
    # `backend_sync.py` imports `DatabaseError` and `salted_hmac` at module
    # level.  Shared with the other five stub loaders so the `salted_hmac`
    # implementation cannot drift — see `tests/django_stubs.py`.
    install_django_stubs(monkeypatch)

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

    # Stub the whole `services` package, not just the one submodule imported
    # below: letting the real `services/__init__.py` run drags in
    # `backend_auth.py`, which imports NetBox models and raises. Without these
    # two entries the file only passed when some earlier test in the same
    # session happened to have populated `sys.modules` first.
    services_pkg = types.ModuleType("netbox_proxbox.services")
    services_pkg.__path__ = [str(REPO_ROOT / "netbox_proxbox" / "services")]
    monkeypatch.setitem(sys.modules, "netbox_proxbox.services", services_pkg)

    endpoint_enabled_mod = types.ModuleType("netbox_proxbox.services.endpoint_enabled")
    # `**kwargs` rather than a bare `endpoint` parameter: the call sites pass the
    # real function's keyword-only `kind=` / `action=`, and a stub that omits them
    # raises `TypeError` from inside the code under test.
    endpoint_enabled_mod.disabled_endpoint_detail = lambda endpoint, **kwargs: (
        None if getattr(endpoint, "enabled", True) else "Endpoint is disabled."
    )
    monkeypatch.setitem(
        sys.modules, "netbox_proxbox.services.endpoint_enabled", endpoint_enabled_mod
    )

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


def _endpoint(
    pk,
    name,
    *,
    enabled=True,
    domain=None,
    ip_address=None,
    port=8006,
    username="root@pam",
    access_methods="api",
    verify_ssl=False,
):
    """Return a Proxmox endpoint stub that resolves a connection target.

    ``domain`` defaults to one derived from ``name`` because the resolvers now
    confirm a backend row still dials the same host, and an endpoint resolving
    no host at all is refused outright. Pass ``domain=""`` for that case.
    """
    return SimpleNamespace(
        pk=pk,
        name=name,
        enabled=enabled,
        domain=name.lower().replace(" ", "-") + ".example.test"
        if domain is None
        else domain,
        ip_address=ip_address,
        port=port,
        username=username,
        access_methods=access_methods,
        verify_ssl=verify_ssl,
    )


def _backend_row(backend_id, endpoint, **overrides):
    """Return the row proxbox-api would store for ``endpoint``, fully current.

    Carries the three pushed fields ``_proxmox_row_is_current()`` compares
    beyond the connection target, so a row built here reads as *held and
    current* unless a test overrides one of them.
    """
    row = {
        "id": backend_id,
        "name": f"{endpoint.name} (nb:{endpoint.pk})",
        "domain": endpoint.domain,
        "ip_address": endpoint.ip_address or "",
        "port": endpoint.port,
        "username": endpoint.username,
        "access_methods": endpoint.access_methods,
        "verify_ssl": endpoint.verify_ssl,
    }
    row.update(overrides)
    return row


def test_proxmox_backend_name_embeds_plugin_pk(monkeypatch):
    backend_sync = _load_backend_sync_module(monkeypatch, endpoints_payload=[])
    assert backend_sync.proxmox_backend_name(_endpoint(3, "PVE")) == "PVE (nb:3)"


def test_resolve_backend_endpoint_id_locates_by_name_and_confirms_the_target(
    monkeypatch,
):
    """Plugin pk 3 must resolve to the backend's own id (7).

    The ``(nb:<pk>)`` name is what *locates* the row; the resolved connection
    target is what *confirms* the row still points at the same Proxmox host.
    """
    endpoint = _endpoint(3, "PVE")
    backend_sync = _load_backend_sync_module(
        monkeypatch,
        endpoints_payload=[
            _backend_row(5, _endpoint(1, "Other")),
            _backend_row(7, endpoint),
        ],
    )
    backend_id, error = backend_sync.resolve_backend_endpoint_id(
        endpoint, base_url="http://backend:8000"
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
        endpoints_payload=[_backend_row(5, _endpoint(1, "Other"))],
    )
    backend_id, error = backend_sync.resolve_backend_endpoint_id(
        _endpoint(3, "PVE"), base_url="http://backend:8000"
    )
    assert backend_id is None
    assert error is not None
    assert "PVE (nb:3)" in error


def test_resolve_backend_endpoint_ids_batches_and_omits_unmatched(monkeypatch):
    """Batch resolution maps matched pks and drops endpoints with no backend row."""
    first, second, third = _endpoint(1, "A"), _endpoint(2, "B"), _endpoint(3, "C")
    backend_sync = _load_backend_sync_module(
        monkeypatch,
        endpoints_payload=[_backend_row(11, first), _backend_row(22, second)],
    )
    mapping, error = backend_sync.resolve_backend_endpoint_ids(
        [first, second, third],
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


def test_resolve_backend_endpoint_id_refuses_a_row_pointing_at_another_host(
    monkeypatch,
):
    """A stale row stored under our own name must be refused, not used.

    This is reachable, not theoretical: the endpoint push runs in the sync
    preflight, where a failure is only *warned* about. Retarget the endpoint in
    NetBox, let that push fail, and proxbox-api still holds the **previous**
    host under this endpoint's name — so syncing through that id would reflect
    the old Proxmox host's inventory into NetBox under the new endpoint.
    """
    endpoint = _endpoint(3, "PVE", domain="new-host.example.test")
    backend_sync = _load_backend_sync_module(
        monkeypatch,
        endpoints_payload=[_backend_row(7, endpoint, domain="old-host.example.test")],
    )

    backend_id, error = backend_sync.resolve_backend_endpoint_id(
        endpoint, base_url="http://backend:8000"
    )

    assert backend_id is None, "a stale row must never be handed to the sync"
    assert error is not None
    assert "old-host.example.test:8006" in error, "say what the backend points at"
    assert "new-host.example.test:8006" in error, "and what it should point at"


def test_resolve_backend_endpoint_id_refuses_a_row_on_a_different_port(monkeypatch):
    """Same host on a different port is a different service."""
    endpoint = _endpoint(3, "PVE")
    backend_sync = _load_backend_sync_module(
        monkeypatch, endpoints_payload=[_backend_row(7, endpoint, port=8007)]
    )

    backend_id, error = backend_sync.resolve_backend_endpoint_id(
        endpoint, base_url="http://backend:8000"
    )

    assert backend_id is None
    assert error is not None and "pve.example.test:8007" in error


def test_resolve_backend_endpoint_id_refuses_a_row_without_a_port(monkeypatch):
    """``port`` is required from the backend, not checked opportunistically.

    proxbox-api declares it non-optional on the ``ProxmoxEndpointPublic`` model
    it returns from ``GET /proxmox/endpoints``, so a row without a parseable one
    is not something this backend produced.
    """
    endpoint = _endpoint(3, "PVE")
    row = _backend_row(7, endpoint)
    del row["port"]
    backend_sync = _load_backend_sync_module(monkeypatch, endpoints_payload=[row])

    backend_id, error = backend_sync.resolve_backend_endpoint_id(
        endpoint, base_url="http://backend:8000"
    )

    assert backend_id is None
    assert error is not None and "resolves no host or port" in error


def test_resolve_backend_endpoint_id_ignores_an_address_change_under_a_domain(
    monkeypatch,
):
    """Our own row stays ours when only the address it never dials changed.

    proxbox-api resolves an endpoint to ``domain or ip_address``, so once a
    domain is set the stored address is a field nobody reads. Comparing the two
    fields side by side instead would reject this row for a difference that
    cannot affect which host is contacted.
    """
    endpoint = _endpoint(3, "PVE", ip_address="10.0.30.9/24")
    backend_sync = _load_backend_sync_module(
        monkeypatch,
        endpoints_payload=[_backend_row(7, endpoint, ip_address="10.0.30.250")],
    )

    backend_id, error = backend_sync.resolve_backend_endpoint_id(
        endpoint, base_url="http://backend:8000"
    )

    assert error is None
    assert backend_id == 7


def test_resolve_backend_endpoint_id_refuses_a_row_matching_only_the_unused_address(
    monkeypatch,
):
    """A stored row blank on ``domain`` at our address is a *different* service.

    It is an endpoint reached by address; ours is reached by vhost name at that
    same address. A blank stored field is data, not a gap — which is the other
    direction a field-by-field comparison gets wrong.
    """
    endpoint = _endpoint(3, "PVE", ip_address="10.0.30.9/24")
    backend_sync = _load_backend_sync_module(
        monkeypatch, endpoints_payload=[_backend_row(7, endpoint, domain="")]
    )

    backend_id, error = backend_sync.resolve_backend_endpoint_id(
        endpoint, base_url="http://backend:8000"
    )

    assert backend_id is None
    assert error is not None and "10.0.30.9:8006" in error


def test_resolve_backend_endpoint_id_refuses_an_endpoint_resolving_no_host(monkeypatch):
    """No resolvable host on our side reads as *not confirmed*, i.e. refused.

    Failing closed costs nothing in practice — ``EndpointBase.clean()`` requires
    a domain or an IP address, so a validly saved row always resolves one.
    """
    endpoint = _endpoint(3, "PVE", domain="")
    backend_sync = _load_backend_sync_module(
        monkeypatch, endpoints_payload=[_backend_row(7, endpoint)]
    )

    backend_id, error = backend_sync.resolve_backend_endpoint_id(
        endpoint, base_url="http://backend:8000"
    )

    assert backend_id is None
    assert error is not None and "resolves no host or port in NetBox" in error


def test_resolve_backend_endpoint_ids_omits_a_stale_row(monkeypatch):
    """Batch resolution drops a stale row rather than mapping it."""
    fresh = _endpoint(1, "A")
    retargeted = _endpoint(2, "B", domain="new-b.example.test")
    backend_sync = _load_backend_sync_module(
        monkeypatch,
        endpoints_payload=[
            _backend_row(11, fresh),
            _backend_row(22, retargeted, domain="old-b.example.test"),
        ],
    )

    mapping, error = backend_sync.resolve_backend_endpoint_ids(
        [fresh, retargeted], base_url="http://backend:8000"
    )

    assert error is None, "one stale endpoint must not fail the whole batch"
    assert mapping == {1: 11}, "the stale endpoint is skipped, not mapped"


def test_backend_holds_proxmox_endpoint_requires_the_row_to_be_current(monkeypatch):
    """The soft push budget may only skip a push that would be a no-op refresh.

    A row whose target or pushed configuration has drifted still needs its push:
    skipping it would preserve exactly the stale row the resolvers then refuse
    to sync against, turning a merely slow backend into a blocked endpoint.
    """
    backend_sync = _load_backend_sync_module(monkeypatch, endpoints_payload=[])
    endpoint = _endpoint(3, "PVE")

    assert backend_sync.backend_holds_proxmox_endpoint(
        endpoint, [_backend_row(7, endpoint)]
    ), "a current row is held"

    drifted = {
        "retargeted": _backend_row(7, endpoint, domain="old-host.example.test"),
        "different port": _backend_row(7, endpoint, port=8007),
        "different user": _backend_row(7, endpoint, username="svc@pve"),
        "different transport": _backend_row(7, endpoint, access_methods="api_ssh"),
        "different tls": _backend_row(7, endpoint, verify_ssl=True),
        "another endpoint": _backend_row(7, _endpoint(4, "Other")),
    }
    for label, row in drifted.items():
        assert not backend_sync.backend_holds_proxmox_endpoint(endpoint, [row]), (
            f"a row with a {label} must still be pushed"
        )

    assert not backend_sync.backend_holds_proxmox_endpoint(endpoint, [])
    assert not backend_sync.backend_holds_proxmox_endpoint(endpoint, None), (
        "a failed listing is unknown, and unknown must never skip a push"
    )
