"""Adversarial tests for backend credential-to-target binding.

These tests exercise the direct ``requests`` surfaces in ``backend_proxy.py``.
Credentialed requests must never follow redirects, and a 401 retry may proceed
only from one freshly authenticated ``BackendRequestContext`` whose complete
URL/header/TLS binding remains stable.
"""

from __future__ import annotations

import importlib
import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests


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

    for module_name in (
        "netbox_proxbox.schemas._base",
        "netbox_proxbox.schemas.backend_proxy",
        "netbox_proxbox.services.backend_auth",
        "netbox_proxbox.services.backend_context",
        "netbox_proxbox.services.backend_key_adoption",
        "netbox_proxbox.services.backend_proxy",
        "netbox_proxbox.services.http_client",
        "netbox_proxbox.utils",
        "netbox_proxbox.views.error_utils",
    ):
        sys.modules.pop(module_name, None)

    return importlib.import_module("netbox_proxbox.services.backend_proxy")


class _Response:
    """Minimal JSON/stream response with observable close behavior."""

    def __init__(
        self,
        status_code: int,
        payload: dict[str, object] | None = None,
        *,
        headers: dict[str, str] | None = None,
        lines: list[str] | None = None,
        url: str = "",
    ) -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self.headers = headers or {}
        self._lines = lines or []
        self.url = url
        self.text = json.dumps(self._payload)
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()
        return False

    def close(self) -> None:
        self.closed = True

    def json(self) -> dict[str, object]:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(
                f"HTTP {self.status_code}",
                response=self,
            )

    def iter_lines(self, decode_unicode: bool = True):
        yield from self._lines


def _context(
    bp,
    *,
    name: str,
    key: str,
    endpoint_id: int = 41,
    use_https: bool = True,
) -> object:
    scheme = "https" if use_https else "http"
    host_number = 1 if name == "a" else 2
    return bp.BackendRequestContext(
        endpoint_id=endpoint_id,
        target_fingerprint=f"fingerprint-{name}",
        http_url=f"{scheme}://{name}.backend.example:8800",
        ip_address_url=f"{scheme}://192.0.2.{host_number}:8800",
        verify_ssl=use_https,
        headers={"X-Proxbox-API-Key": key},
    )


def _complete_lines() -> list[str]:
    return [
        "event: complete",
        f"data: {json.dumps({'ok': True, 'message': 'done'})}",
        "",
    ]


def test_cross_origin_json_redirect_never_receives_api_key(
    backend_proxy_module,
    monkeypatch,
):
    bp = backend_proxy_module
    context = _context(bp, name="a", key="key-a")
    redirect_target = "https://attacker.example/collect"
    redirect = _Response(
        302,
        headers={"Location": redirect_target},
        url=f"{context.http_url}/extras/bootstrap-status",
    )
    calls: list[tuple[str, dict[str, object]]] = []

    def fake_get(url: str, **kwargs):
        calls.append((url, kwargs))
        return redirect

    monkeypatch.setattr(bp.requests, "get", fake_get)

    payload, status = bp.request_backend_json(context, "extras/bootstrap-status")

    assert status == 502
    assert payload["ok"] is False
    assert "redirects are not permitted" in str(payload["detail"])
    assert redirect.closed
    assert len(calls) == 1
    assert calls[0][0] == f"{context.http_url}/extras/bootstrap-status"
    assert calls[0][1]["headers"]["X-Proxbox-API-Key"] == "key-a"
    assert calls[0][1]["allow_redirects"] is False
    assert all(url != redirect_target for url, _kwargs in calls)


def test_https_to_http_downgrade_redirect_is_terminal(
    backend_proxy_module,
    monkeypatch,
):
    bp = backend_proxy_module
    context = _context(bp, name="a", key="key-a")
    redirect = _Response(
        307,
        headers={"Location": "http://a.backend.example:8800/proxmox/version"},
    )
    calls: list[tuple[str, dict[str, object]]] = []

    def fake_get(url: str, **kwargs):
        calls.append((url, kwargs))
        return redirect

    monkeypatch.setattr(bp.requests, "get", fake_get)

    payload, status = bp.request_backend_resource(context, "proxmox/version")

    assert status == 502
    assert payload["queued"] is False
    assert redirect.closed
    assert calls == [
        (
            "https://a.backend.example:8800/proxmox/version",
            {
                "params": None,
                "headers": {"X-Proxbox-API-Key": "key-a"},
                "verify": True,
                "timeout": 5,
                "allow_redirects": False,
            },
        )
    ]


def test_run_sync_stream_refuses_redirect_without_fallback(
    backend_proxy_module,
    monkeypatch,
):
    bp = backend_proxy_module
    context = _context(bp, name="a", key="key-a")
    redirect = _Response(
        302,
        headers={"Location": "https://stream-attacker.example/collect"},
    )
    calls: list[tuple[str, dict[str, object]]] = []

    monkeypatch.setattr(bp, "get_fastapi_request_context", lambda: context)
    monkeypatch.setattr(bp, "wait_for_backend_ready", lambda _context: (True, "ok"))

    def fake_get(url: str, **kwargs):
        calls.append((url, kwargs))
        return redirect

    monkeypatch.setattr(bp.requests, "get", fake_get)

    payload, status = bp.run_sync_stream("full-update/stream")

    assert status == 502
    assert "redirects are not permitted" in str(payload["detail"])
    assert redirect.closed
    assert len(calls) == 1
    assert calls[0][0] == "https://a.backend.example:8800/full-update/stream"
    assert calls[0][1]["allow_redirects"] is False
    assert calls[0][1]["stream"] is True


def test_iter_backend_sse_lines_refuses_redirect_without_fallback(
    backend_proxy_module,
    monkeypatch,
):
    bp = backend_proxy_module
    context = _context(bp, name="a", key="key-a")
    redirect = _Response(
        308,
        headers={"Location": "https://stream-attacker.example/collect"},
    )
    calls: list[tuple[str, dict[str, object]]] = []

    def fake_get(url: str, **kwargs):
        calls.append((url, kwargs))
        return redirect

    monkeypatch.setattr(bp.requests, "get", fake_get)

    lines = list(bp.iter_backend_sse_lines(context, "full-update/stream"))

    assert redirect.closed
    assert len(calls) == 1
    assert calls[0][0] == "https://a.backend.example:8800/full-update/stream"
    assert calls[0][1]["allow_redirects"] is False
    assert "redirects are not permitted" in "".join(lines)


def test_rotated_endpoint_401_retry_none_path_fails_closed(
    backend_proxy_module,
    monkeypatch,
):
    """If endpoint A becomes B while rebinding, no mixed request is emitted."""
    bp = backend_proxy_module
    context_a = _context(bp, name="a", key="key-a", endpoint_id=41)
    context_b = _context(bp, name="b", key="key-b", endpoint_id=42)
    unauthorized = _Response(401, {"detail": "Invalid API key"})
    calls: list[tuple[str, dict[str, object]]] = []
    retry_calls: list[tuple[object, int | None]] = []

    def fake_get(url: str, **kwargs):
        calls.append((url, kwargs))
        return unauthorized

    def fail_closed_retry(context, *, endpoint_id=None):
        retry_calls.append((context, endpoint_id))
        assert context == context_a
        assert context_b.endpoint_id != context.endpoint_id
        return None

    monkeypatch.setattr(bp.requests, "get", fake_get)
    monkeypatch.setattr(
        bp,
        "_handle_auth_registration_and_retry",
        fail_closed_retry,
    )

    payload, status = bp.request_backend_json(
        context_a,
        "extras/bootstrap-status",
        endpoint_id=41,
    )

    assert status == 401
    assert payload["ok"] is False
    assert unauthorized.closed
    assert retry_calls == [(context_a, 41)]
    assert [(url, kwargs["headers"]) for url, kwargs in calls] == [
        (
            "https://a.backend.example:8800/extras/bootstrap-status",
            {"X-Proxbox-API-Key": "key-a"},
        )
    ]


def test_json_401_retry_restarts_from_fresh_urls_and_headers(
    backend_proxy_module,
    monkeypatch,
):
    bp = backend_proxy_module
    context_a = _context(bp, name="a", key="key-a")
    context_b = _context(bp, name="b", key="key-b")
    responses = [
        _Response(401, {"detail": "Invalid API key"}),
        _Response(200, {"state": "ready"}),
    ]
    calls: list[tuple[str, dict[str, object]]] = []

    def fake_get(url: str, **kwargs):
        calls.append((url, kwargs))
        return responses.pop(0)

    monkeypatch.setattr(bp.requests, "get", fake_get)
    monkeypatch.setattr(
        bp,
        "_handle_auth_registration_and_retry",
        lambda context, *, endpoint_id=None: context_b,
    )

    payload, status = bp.request_backend_json(
        context_a,
        "extras/bootstrap-status",
        endpoint_id=41,
    )

    assert status == 200
    assert payload["response"] == {"state": "ready"}
    assert [(url, kwargs["headers"], kwargs["verify"]) for url, kwargs in calls] == [
        (
            "https://a.backend.example:8800/extras/bootstrap-status",
            {"X-Proxbox-API-Key": "key-a"},
            True,
        ),
        (
            "https://b.backend.example:8800/extras/bootstrap-status",
            {"X-Proxbox-API-Key": "key-b"},
            True,
        ),
    ]
    assert all(kwargs["allow_redirects"] is False for _url, kwargs in calls)


def test_resource_401_retry_restarts_and_binds_context_endpoint_id(
    backend_proxy_module,
    monkeypatch,
):
    bp = backend_proxy_module
    context_a = _context(bp, name="a", key="key-a", endpoint_id=41)
    context_b = _context(bp, name="b", key="key-b", endpoint_id=41)
    responses = [
        _Response(401, {"detail": "Invalid API key"}),
        _Response(200, {"version": "0.0.18"}),
    ]
    calls: list[tuple[str, dict[str, object]]] = []
    retry_calls: list[tuple[object, int | None]] = []

    def fake_get(url: str, **kwargs):
        calls.append((url, kwargs))
        return responses.pop(0)

    def retry(context, *, endpoint_id=None):
        retry_calls.append((context, endpoint_id))
        return context_b

    monkeypatch.setattr(bp.requests, "get", fake_get)
    monkeypatch.setattr(bp, "_handle_auth_registration_and_retry", retry)

    payload, status = bp.request_backend_resource(context_a, "proxmox/version")

    assert status == 202
    assert payload["response"] == {"version": "0.0.18"}
    assert retry_calls == [(context_a, 41)]
    assert [(url, kwargs["headers"]) for url, kwargs in calls] == [
        (
            "https://a.backend.example:8800/proxmox/version",
            {"X-Proxbox-API-Key": "key-a"},
        ),
        (
            "https://b.backend.example:8800/proxmox/version",
            {"X-Proxbox-API-Key": "key-b"},
        ),
    ]


def test_run_sync_stream_401_retry_restarts_from_fresh_context(
    backend_proxy_module,
    monkeypatch,
):
    bp = backend_proxy_module
    context_a = _context(bp, name="a", key="key-a")
    context_b = _context(bp, name="b", key="key-b")
    responses = [
        _Response(401, {"detail": "Invalid API key"}),
        _Response(200, lines=_complete_lines()),
    ]
    calls: list[tuple[str, dict[str, object]]] = []

    monkeypatch.setattr(bp, "get_fastapi_request_context", lambda: context_a)
    monkeypatch.setattr(bp, "wait_for_backend_ready", lambda _context: (True, "ok"))
    monkeypatch.setattr(
        bp,
        "_handle_auth_registration_and_retry",
        lambda context, *, endpoint_id=None: context_b,
    )

    def fake_get(url: str, **kwargs):
        calls.append((url, kwargs))
        return responses.pop(0)

    monkeypatch.setattr(bp.requests, "get", fake_get)

    payload, status = bp.run_sync_stream("full-update/stream")

    assert status == 200
    assert payload["response"]["ok"] is True
    assert [(url, kwargs["headers"]) for url, kwargs in calls] == [
        (
            "https://a.backend.example:8800/full-update/stream",
            {"X-Proxbox-API-Key": "key-a"},
        ),
        (
            "https://b.backend.example:8800/full-update/stream",
            {"X-Proxbox-API-Key": "key-b"},
        ),
    ]
    assert all(kwargs["allow_redirects"] is False for _url, kwargs in calls)


def test_stale_related_ip_fingerprint_drift_returns_no_context(
    backend_proxy_module,
):
    """A stale cached IP object cannot mask a changed live FK address."""
    import netbox_proxbox.services.backend_key_adoption as adoption
    import netbox_proxbox.utils as utils

    live_ip = {"address": "192.0.2.10/32"}
    endpoint = SimpleNamespace(
        pk=41,
        enabled=True,
        domain="a.backend.example",
        ip_address=SimpleNamespace(address="192.0.2.10/32"),
        port=8800,
        use_https=True,
        verify_ssl=True,
        use_websocket=False,
        websocket_domain=None,
        websocket_port=None,
        server_side_websocket=False,
        token="key-a",
        backend_key_ip_address_for_trust=lambda: live_ip["address"],
    )
    endpoint.backend_key_target_fingerprint = adoption.backend_key_target_fingerprint(
        endpoint
    )

    live_ip["address"] = "192.0.2.11/32"

    assert str(endpoint.ip_address.address) == "192.0.2.10/32"
    assert utils.get_fastapi_context(endpoint) is None


def test_concurrent_binding_change_during_auth_retry_fails_closed(
    backend_proxy_module,
    monkeypatch,
):
    bp = backend_proxy_module
    backend_context = importlib.import_module("netbox_proxbox.services.backend_context")
    backend_auth = importlib.import_module("netbox_proxbox.services.backend_auth")
    original = _context(bp, name="a", key="key-a")
    authenticated = _context(bp, name="b", key="key-b")
    concurrently_changed = bp.BackendRequestContext(
        endpoint_id=authenticated.endpoint_id,
        target_fingerprint="fingerprint-c",
        http_url=authenticated.http_url,
        ip_address_url=authenticated.ip_address_url,
        verify_ssl=authenticated.verify_ssl,
        headers={"X-Proxbox-API-Key": "key-c"},
    )
    resolved_contexts = iter([authenticated, concurrently_changed])
    authenticated_contexts: list[object] = []

    monkeypatch.setattr(
        backend_context,
        "get_fastapi_request_context",
        lambda endpoint_id=None: next(resolved_contexts),
    )

    def authenticate(context):
        authenticated_contexts.append(context)
        return True, "authenticated"

    monkeypatch.setattr(
        backend_auth,
        "authenticate_backend_request_context",
        authenticate,
    )

    result = backend_context._handle_auth_registration_and_retry(
        original,
        endpoint_id=41,
    )

    assert result is None
    assert authenticated_contexts == [authenticated]
