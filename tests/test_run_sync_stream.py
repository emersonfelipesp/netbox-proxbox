"""Tests for ``run_sync_stream`` (SSE consumption for background sync jobs)."""

from __future__ import annotations

import importlib
import json
import sys
import types
from pathlib import Path

import pytest


@pytest.fixture
def backend_proxy_module(monkeypatch):
    """Load backend proxy helpers with the minimum NetBox stubs."""
    repo_root = Path(__file__).resolve().parents[1]

    netbox_module = types.ModuleType("netbox")
    netbox_plugins = types.ModuleType("netbox.plugins")
    netbox_plugins.PluginConfig = type("PluginConfig", (), {})
    monkeypatch.setitem(sys.modules, "netbox", netbox_module)
    monkeypatch.setitem(sys.modules, "netbox.plugins", netbox_plugins)

    nbp_root = types.ModuleType("netbox_proxbox")
    nbp_root.__path__ = [str(repo_root / "netbox_proxbox")]
    monkeypatch.setitem(sys.modules, "netbox_proxbox", nbp_root)

    nbp_views = types.ModuleType("netbox_proxbox.views")
    nbp_views.__path__ = [str(repo_root / "netbox_proxbox" / "views")]
    monkeypatch.setitem(sys.modules, "netbox_proxbox.views", nbp_views)

    nbp_schemas = types.ModuleType("netbox_proxbox.schemas")
    nbp_schemas.__path__ = [str(repo_root / "netbox_proxbox" / "schemas")]
    monkeypatch.setitem(sys.modules, "netbox_proxbox.schemas", nbp_schemas)

    nbp_services = types.ModuleType("netbox_proxbox.services")
    nbp_services.__path__ = [str(repo_root / "netbox_proxbox" / "services")]
    monkeypatch.setitem(sys.modules, "netbox_proxbox.services", nbp_services)

    models_stub = types.ModuleType("netbox_proxbox.models")
    models_stub.FastAPIEndpoint = type("FastAPIEndpoint", (), {})
    monkeypatch.setitem(sys.modules, "netbox_proxbox.models", models_stub)

    sys.modules.pop("netbox_proxbox.services.backend_proxy", None)
    sys.modules.pop("netbox_proxbox.utils", None)
    sys.modules.pop("netbox_proxbox.views.error_utils", None)
    sys.modules.pop("netbox_proxbox.schemas.backend_proxy", None)
    sys.modules.pop("netbox_proxbox.schemas._base", None)

    return importlib.import_module("netbox_proxbox.services.backend_proxy")


class _StreamResponse:
    """Minimal streaming ``requests`` response for ``with requests.get(..., stream=True)``."""

    def __init__(self, lines: list[str], *, status_code: int = 200):
        self.status_code = status_code
        self._lines = lines

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def iter_lines(self, decode_unicode: bool = True):
        yield from self._lines


class _ErrorBodyResponse:
    """Non-stream error response with JSON body."""

    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def json(self):
        return self._payload


def _sse_complete_ok() -> list[str]:
    return [
        "event: step",
        f"data: {json.dumps({'step': 'devices', 'status': 'started'})}",
        "",
        "event: complete",
        f"data: {json.dumps({'ok': True, 'message': 'done', 'result': {'n': 3}})}",
        "",
    ]


def _stream_context(bp):
    return bp.BackendRequestContext(
        http_url="https://proxbox.local:8800",
        ip_address_url="https://10.0.0.5:8800",
        verify_ssl=True,
        headers={"Authorization": "Bearer backend-token"},
    )


def test_run_sync_stream_success(backend_proxy_module, monkeypatch):
    bp = backend_proxy_module
    urls: list[str] = []

    def fake_get(url, **kwargs):
        urls.append(url)
        assert kwargs.get("stream") is True
        assert kwargs.get("verify") is True
        return _StreamResponse(_sse_complete_ok())

    monkeypatch.setattr(bp.requests, "get", fake_get)
    monkeypatch.setattr(bp, "get_fastapi_request_context", lambda: _stream_context(bp))

    frames: list[tuple[str, dict]] = []

    def on_frame(ev: str, data: dict) -> None:
        frames.append((ev, data))

    payload, status = bp.run_sync_stream(
        "dcim/devices/create/stream",
        query_params={"proxmox_endpoint_ids": "1,2"},
        on_frame=on_frame,
    )
    assert [f[0] for f in frames] == ["step", "complete"]
    assert status == 200
    assert payload["stream"] is True
    assert payload["response"]["ok"] is True
    assert payload["response"]["result"]["n"] == 3
    assert payload["path"] == "dcim/devices/create/stream"
    assert urls[0].startswith("https://proxbox.local:8800/dcim/devices/create/stream")


def test_run_sync_stream_complete_ok_false(backend_proxy_module, monkeypatch):
    bp = backend_proxy_module
    lines = [
        "event: error",
        f"data: {json.dumps({'detail': 'x'})}",
        "",
        "event: complete",
        f"data: {json.dumps({'ok': False, 'message': 'failed', 'errors': [{'detail': 'boom'}]})}",
        "",
    ]
    monkeypatch.setattr(
        bp.requests,
        "get",
        lambda *a, **k: _StreamResponse(lines),
    )
    monkeypatch.setattr(bp, "get_fastapi_request_context", lambda: _stream_context(bp))
    payload, status = bp.run_sync_stream("full-update/stream")
    assert status == 503
    assert "boom" in (payload.get("detail") or "")


def test_run_sync_stream_missing_complete(backend_proxy_module, monkeypatch):
    bp = backend_proxy_module
    lines = [
        "event: step",
        f"data: {json.dumps({'x': 1})}",
        "",
    ]
    monkeypatch.setattr(
        bp.requests,
        "get",
        lambda *a, **k: _StreamResponse(lines),
    )
    monkeypatch.setattr(bp, "get_fastapi_request_context", lambda: _stream_context(bp))
    payload, status = bp.run_sync_stream("dcim/devices/create/stream")
    assert status == 502
    assert "without a complete" in payload["detail"]


def test_run_sync_stream_http_error_json(backend_proxy_module, monkeypatch):
    bp = backend_proxy_module
    monkeypatch.setattr(
        bp.requests,
        "get",
        lambda *a, **k: _ErrorBodyResponse(502, {"detail": "bad gateway"}),
    )
    monkeypatch.setattr(bp, "get_fastapi_request_context", lambda: _stream_context(bp))
    payload, status = bp.run_sync_stream("dcim/devices/create/stream")
    assert status == 503
    assert payload["detail"] == "bad gateway"


def test_run_sync_stream_no_fastapi_url(backend_proxy_module, monkeypatch):
    bp = backend_proxy_module
    monkeypatch.setattr(bp, "get_fastapi_request_context", lambda: None)
    payload, status = bp.run_sync_stream("full-update/stream")
    assert status == 404
    assert "No FastAPI URL" in payload["detail"]
