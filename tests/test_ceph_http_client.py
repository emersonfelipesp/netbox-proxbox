"""Behavior tests for ``netbox_ceph.services.http_client``.

Pins the read-only contract this plugin uses against the companion
``proxbox-api`` Ceph routes:

* ``CEPH_SYNC_RESOURCES`` matches the v1 backend surface exactly.
* ``fetch_ceph_sync`` rejects unknown resources with ``ValueError``
  before any HTTP work happens.
* ``fetch_ceph_sync`` threads ``netbox_branch_schema_id`` through the
  query string only when provided.
* ``fetch_ceph_sync`` raises ``CephBackendError`` when the configured
  FastAPIEndpoint context is missing, or when the upstream returns a
  non-2xx response, non-JSON body, or non-dict payload.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import types
from types import SimpleNamespace

import pytest


REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
HTTP_CLIENT_PATH = (
    REPO_ROOT / "netbox_ceph" / "netbox_ceph" / "services" / "http_client.py"
)


def _install_http_client(
    monkeypatch: pytest.MonkeyPatch,
    *,
    context: object | None,
    fake_requests: object,
) -> object:
    for name in (
        "netbox_proxbox",
        "netbox_proxbox.services",
        "netbox_proxbox.services.backend_context",
        "netbox_ceph",
        "netbox_ceph.services",
    ):
        pkg = types.ModuleType(name)
        pkg.__path__ = []  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, name, pkg)

    backend_ctx = sys.modules["netbox_proxbox.services.backend_context"]

    def get_fastapi_request_context() -> object | None:
        return context

    backend_ctx.get_fastapi_request_context = get_fastapi_request_context  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "requests", fake_requests)

    sys.modules.pop("netbox_ceph.services.http_client", None)
    spec = importlib.util.spec_from_file_location(
        "netbox_ceph.services.http_client",
        HTTP_CLIENT_PATH,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["netbox_ceph.services.http_client"] = module
    spec.loader.exec_module(module)
    return module


class _FakeResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        payload: object = None,
        body: str | None = None,
    ) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = body if body is not None else "" if payload is None else "ok"

    def json(self) -> object:
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class _FakeRequests:
    """Minimal ``requests`` stand-in capturing the last GET call."""

    class RequestException(Exception):
        pass

    def __init__(self, response: _FakeResponse | Exception):
        self._response = response
        self.last_call: dict[str, object] | None = None

    def get(self, url: str, **kwargs: object) -> _FakeResponse:
        self.last_call = {"url": url, **kwargs}
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


def _good_context() -> SimpleNamespace:
    return SimpleNamespace(
        http_url="http://proxbox-api.example/",
        headers={"X-Proxbox-API-Key": "abc"},
        verify_ssl=True,
    )


def test_resources_match_backend_v1_contract(monkeypatch):
    mod = _install_http_client(
        monkeypatch,
        context=_good_context(),
        fake_requests=_FakeRequests(_FakeResponse(payload={"items": []})),
    )
    assert mod.CEPH_SYNC_RESOURCES == (
        "status",
        "daemons",
        "osds",
        "pools",
        "filesystems",
        "crush",
        "flags",
        "full",
    )


def test_fetch_ceph_sync_rejects_unknown_resource(monkeypatch):
    mod = _install_http_client(
        monkeypatch,
        context=_good_context(),
        fake_requests=_FakeRequests(_FakeResponse(payload={"items": []})),
    )
    with pytest.raises(ValueError, match="Unknown Ceph sync resource"):
        mod.fetch_ceph_sync("not-a-real-resource")


def test_fetch_ceph_sync_passes_branch_schema_id(monkeypatch):
    fake = _FakeRequests(_FakeResponse(payload={"items": []}))
    mod = _install_http_client(monkeypatch, context=_good_context(), fake_requests=fake)

    result = mod.fetch_ceph_sync("full", netbox_branch_schema_id="schema_42")
    assert result == {"items": []}
    assert fake.last_call is not None
    assert fake.last_call["url"] == "http://proxbox-api.example/ceph/sync/full"
    assert fake.last_call["params"] == {"netbox_branch_schema_id": "schema_42"}
    assert fake.last_call["verify"] is True
    assert fake.last_call["headers"] == {"X-Proxbox-API-Key": "abc"}


def test_fetch_ceph_sync_omits_params_when_no_branch(monkeypatch):
    fake = _FakeRequests(_FakeResponse(payload={"items": []}))
    mod = _install_http_client(monkeypatch, context=_good_context(), fake_requests=fake)

    mod.fetch_ceph_sync("status")
    assert fake.last_call is not None
    assert fake.last_call["params"] is None


def test_fetch_ceph_status_uses_status_route(monkeypatch):
    fake = _FakeRequests(_FakeResponse(payload={"items": [{"reachable": True}]}))
    mod = _install_http_client(monkeypatch, context=_good_context(), fake_requests=fake)

    payload = mod.fetch_ceph_status()
    assert payload == {"items": [{"reachable": True}]}
    assert fake.last_call is not None
    assert fake.last_call["url"] == "http://proxbox-api.example/ceph/status"


def test_missing_fastapi_context_raises(monkeypatch):
    mod = _install_http_client(
        monkeypatch,
        context=None,
        fake_requests=_FakeRequests(_FakeResponse(payload={})),
    )
    with pytest.raises(mod.CephBackendError, match="No FastAPIEndpoint configured"):
        mod.fetch_ceph_status()


def test_non_2xx_response_raises_backend_error(monkeypatch):
    fake = _FakeRequests(_FakeResponse(status_code=503, body="upstream down"))
    mod = _install_http_client(monkeypatch, context=_good_context(), fake_requests=fake)
    with pytest.raises(mod.CephBackendError, match="HTTP 503"):
        mod.fetch_ceph_sync("status")


def test_non_dict_payload_raises_backend_error(monkeypatch):
    fake = _FakeRequests(_FakeResponse(payload=["not-a-dict"]))
    mod = _install_http_client(monkeypatch, context=_good_context(), fake_requests=fake)
    with pytest.raises(mod.CephBackendError, match="unexpected payload shape"):
        mod.fetch_ceph_sync("status")


def test_request_exception_translates_to_backend_error(monkeypatch):
    fake = _FakeRequests(_FakeRequests.RequestException("conn refused"))
    mod = _install_http_client(monkeypatch, context=_good_context(), fake_requests=fake)
    # Patch fake.RequestException onto fake_requests so the http_client's
    # `except requests.RequestException` catches it cleanly.
    with pytest.raises(mod.CephBackendError, match="Ceph backend request failed"):
        mod.fetch_ceph_sync("status")
