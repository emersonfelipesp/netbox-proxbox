from __future__ import annotations

import importlib
from types import SimpleNamespace

import requests

from tests.conftest import ResponseStub, load_plugin_module


def _service_status_module():
    return importlib.import_module("netbox_proxbox.services.service_status")


def test_fastapi_status_falls_back_to_ip_after_ssl_error(
    monkeypatch,
    fastapi_endpoint,
):
    load_plugin_module(
        "netbox_proxbox.views.keepalive_status",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
    )
    ss = _service_status_module()
    calls = []

    def fake_get(url, verify=True, timeout=None):
        calls.append((url, verify))
        if "proxbox.local" in url:
            raise requests.exceptions.SSLError("bad cert")
        return ResponseStub({"ok": True})

    monkeypatch.setattr(ss.requests, "get", fake_get)

    status = ss.ServiceStatus().fastapi_status(1)
    assert status["connected"] is True
    assert status["connected_verify_ssl"] is False
    assert calls == [
        ("https://proxbox.local:8800", True),
        ("https://10.0.0.5:8800", False),
    ]


def test_netbox_status_succeeds_without_backend_round_trip(
    monkeypatch,
    fastapi_endpoint,
    netbox_endpoint,
):
    load_plugin_module(
        "netbox_proxbox.views.keepalive_status",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
        netbox_endpoint=netbox_endpoint,
    )
    ss = _service_status_module()
    monkeypatch.setattr(ss.time, "sleep", lambda seconds: None)

    monkeypatch.setattr(
        ss.requests,
        "get",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("netbox keepalive must not call the backend")
        ),
    )

    status, details = ss.ServiceStatus().netbox_status(
        1,
        "https://proxbox.local:8800",
        auth_headers={"Authorization": "Bearer backend-token"},
    )
    assert status == "success"
    assert details["api_access"] == "success"
    assert details["authentication"] == "success"
    assert details["target_address"] == "netbox.local"
    assert details["target_port"] == 443


def test_netbox_status_v2_without_secret_fails_backend_validation(
    monkeypatch,
    fastapi_endpoint,
):
    netbox_endpoint = SimpleNamespace(
        id=1,
        pk=1,
        name="netbox",
        domain="netbox.local",
        ip_address=SimpleNamespace(address="10.0.0.20/24"),
        port=443,
        token=SimpleNamespace(version=2, key="v2-token-key"),
        effective_token_value="v2-token-key",
        effective_token_version="v2",
        token_key="",
        token_secret="",
        verify_ssl=True,
    )
    load_plugin_module(
        "netbox_proxbox.views.keepalive_status",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
        netbox_endpoint=netbox_endpoint,
    )
    ss = _service_status_module()
    monkeypatch.setattr(ss.time, "sleep", lambda seconds: None)

    service_status = ss.ServiceStatus()
    status, details = service_status.netbox_status(
        1,
        "https://proxbox.local:8800",
        auth_headers={"Authorization": "Bearer backend-token"},
    )
    assert status == "error"
    assert details["api_access"] == "error"
    assert service_status.last_error_detail == (
        "NetBox v2 credentials are incomplete. Provide both token key and token secret."
    )


def test_netbox_status_builds_full_v2_token_from_key_and_secret(
    monkeypatch,
    fastapi_endpoint,
):
    netbox_endpoint = SimpleNamespace(
        id=1,
        pk=1,
        name="netbox",
        domain=None,
        ip_address="10.0.0.20/24",
        port=8000,
        token=None,
        effective_token_value="v2-token-key",
        effective_token_version="v2",
        token_key="v2-token-key",
        token_secret="v2-token-secret",
        verify_ssl=False,
    )
    load_plugin_module(
        "netbox_proxbox.views.keepalive_status",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
        netbox_endpoint=netbox_endpoint,
    )
    ss = _service_status_module()
    monkeypatch.setattr(ss.time, "sleep", lambda seconds: None)

    monkeypatch.setattr(
        ss.requests,
        "get",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("netbox keepalive must not call the backend")
        ),
    )

    status, details = ss.ServiceStatus().netbox_status(
        1,
        "https://proxbox.local:8800",
        auth_headers={"Authorization": "Bearer backend-token"},
    )
    assert status == "success"
    assert details["api_access"] == "success"


def test_backend_auth_headers_accepts_prefixed_and_bare_tokens(
    monkeypatch,
    fastapi_endpoint,
):
    load_plugin_module(
        "netbox_proxbox.views.keepalive_status",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
    )
    ss = _service_status_module()

    assert ss.ServiceStatus.backend_auth_headers(None) == {}
    assert ss.ServiceStatus.backend_auth_headers(SimpleNamespace(token="")) == {}
    assert ss.ServiceStatus.backend_auth_headers(
        SimpleNamespace(token="Bearer abc")
    ) == {"Authorization": "Bearer abc"}
    assert ss.ServiceStatus.backend_auth_headers(
        SimpleNamespace(token="Token abc")
    ) == {"Authorization": "Token abc"}
    assert ss.ServiceStatus.backend_auth_headers(SimpleNamespace(token="abc")) == {
        "Authorization": "Bearer abc"
    }


def test_netbox_status_ignores_backend_auth_headers_for_local_validation(
    monkeypatch,
    fastapi_endpoint,
    netbox_endpoint,
):
    load_plugin_module(
        "netbox_proxbox.views.keepalive_status",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
        netbox_endpoint=netbox_endpoint,
    )
    ss = _service_status_module()
    monkeypatch.setattr(ss.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(
        ss.requests,
        "get",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("netbox keepalive must not call the backend")
        ),
    )

    service_status = ss.ServiceStatus()
    status, details = service_status.netbox_status(
        1,
        "https://proxbox.local:8800",
        auth_headers={"Authorization": "Bearer backend-token", "X-Test": "1"},
    )

    assert status == "success"
    assert details["api_access"] == "success"
    assert details["authentication"] == "success"
    assert service_status.last_error_detail is None
    assert service_status.last_error_http_status is None


def test_extract_error_detail_identifies_html_404_from_wrong_backend_target(
    monkeypatch,
    fastapi_endpoint,
):
    load_plugin_module(
        "netbox_proxbox.views.keepalive_status",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
    )
    ss = _service_status_module()

    class Html404Response(ResponseStub):
        def __init__(self):
            super().__init__(payload={}, status_code=404)
            self.text = "<!DOCTYPE html><html><body>Page Not Found</body></html>"
            self.headers = {"Content-Type": "text/html; charset=utf-8"}
            self.url = "http://10.0.30.206:8000/netbox/endpoint"

    err = requests.exceptions.HTTPError("404")
    err.response = Html404Response()

    detail, status = ss.ServiceStatus._extract_error_detail(err)

    assert status == 404
    assert "Backend returned HTML instead of ProxBox API JSON" in detail
    assert "pointing to NetBox UI instead of proxbox-api" in detail


def test_extract_error_detail_rewrites_connection_refused_to_clear_backend_message(
    monkeypatch,
    fastapi_endpoint,
):
    load_plugin_module(
        "netbox_proxbox.views.keepalive_status",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
    )
    ss = _service_status_module()

    err = requests.exceptions.ConnectionError(
        "HTTPConnectionPool(host='10.0.30.207', port=8000): Max retries exceeded "
        "with url: / (Caused by NewConnectionError(\"Failed to establish a new "
        "connection: [Errno 111] Connection refused\"))"
    )

    detail, status = ss.ServiceStatus._extract_error_detail(err)

    assert status is None
    assert "Unable to reach ProxBox backend at 10.0.30.207:8000" in detail
    assert "Connection was refused" in detail
    assert "Verify proxbox-api is running" in detail


def test_extract_error_detail_rewrites_timeout_to_clear_backend_message(
    monkeypatch,
    fastapi_endpoint,
):
    load_plugin_module(
        "netbox_proxbox.views.keepalive_status",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
    )
    ss = _service_status_module()

    err = requests.exceptions.ReadTimeout(
        "HTTPConnectionPool(host='10.0.30.207', port=8000): Read timed out. "
        "(read timeout=5)"
    )

    detail, status = ss.ServiceStatus._extract_error_detail(err)

    assert status is None
    assert "Timed out while connecting to ProxBox backend at 10.0.30.207:8000" in detail
    assert "Verify network reachability" in detail


def test_proxmox_status_uses_domain_query_when_available(
    monkeypatch,
    fastapi_endpoint,
    proxmox_endpoint,
):
    load_plugin_module(
        "netbox_proxbox.views.keepalive_status",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
        proxmox_endpoint=proxmox_endpoint,
    )
    ss = _service_status_module()
    monkeypatch.setattr(ss.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(
        ss,
        "sync_proxmox_endpoint_to_backend",
        lambda *args, **kwargs: (True, None, None),
    )
    requested = []

    def fake_get(url, verify=True, timeout=None, params=None, headers=None):
        requested.append((url, params, headers, verify))
        return ResponseStub([{"pve01": {"version": "8.3.0"}}])

    monkeypatch.setattr(ss.requests, "get", fake_get)

    status, details = ss.ServiceStatus().proxmox_status(
        1,
        "https://proxbox.local:8800",
        auth_headers={"Authorization": "Bearer backend-token"},
        backend_verify_ssl=True,
    )
    assert status == "success"
    assert details["api_access"] == "success"
    assert requested == [
        (
            "https://proxbox.local:8800/proxmox/version",
            {"source": "database", "domain": "pve.local"},
            {"Authorization": "Bearer backend-token"},
            True,
        )
    ]


def test_proxmox_status_uses_ip_query_when_domain_missing(
    monkeypatch,
    fastapi_endpoint,
):
    proxmox_endpoint = SimpleNamespace(
        id=1,
        name="pve01",
        domain="",
        ip_address="10.0.0.30/24",
        port=8006,
        verify_ssl=False,
    )
    load_plugin_module(
        "netbox_proxbox.views.keepalive_status",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
        proxmox_endpoint=proxmox_endpoint,
    )
    ss = _service_status_module()
    monkeypatch.setattr(
        ss,
        "sync_proxmox_endpoint_to_backend",
        lambda *args, **kwargs: (True, None, None),
    )
    requested = []

    def fake_get(url, verify=True, timeout=None, params=None, headers=None):
        requested.append((url, params, headers, verify))
        return ResponseStub([{"pve01": {"version": "8.3.0"}}])

    monkeypatch.setattr(ss.requests, "get", fake_get)

    status, details = ss.ServiceStatus().proxmox_status(
        1,
        "https://proxbox.local:8800",
        auth_headers={"Authorization": "Bearer backend-token"},
        backend_verify_ssl=False,
    )
    assert status == "success"
    assert details["api_access"] == "success"
    assert requested == [
        (
            "https://proxbox.local:8800/proxmox/version",
            {"source": "database", "ip_address": "10.0.0.30"},
            {"Authorization": "Bearer backend-token"},
            False,
        )
    ]


def test_proxmox_status_normalizes_backend_connection_refused(
    monkeypatch,
    fastapi_endpoint,
    proxmox_endpoint,
):
    load_plugin_module(
        "netbox_proxbox.views.keepalive_status",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
        proxmox_endpoint=proxmox_endpoint,
    )
    ss = _service_status_module()
    monkeypatch.setattr(ss.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(
        ss,
        "sync_proxmox_endpoint_to_backend",
        lambda *args, **kwargs: (True, None, None),
    )

    def fake_get(url, verify=True, timeout=None, params=None, headers=None):
        raise requests.exceptions.ConnectionError(
            "HTTPConnectionPool(host='10.0.30.207', port=8000): Max retries exceeded "
            "with url: /proxmox/version?source=database&domain=pve.local "
            '(Caused by NewConnectionError("Failed to establish a new connection: '
            '[Errno 111] Connection refused"))'
        )

    monkeypatch.setattr(ss.requests, "get", fake_get)

    service_status = ss.ServiceStatus()
    status, details = service_status.proxmox_status(
        1,
        "https://proxbox.local:8800",
        auth_headers={"Authorization": "Bearer backend-token"},
        backend_verify_ssl=True,
    )

    assert status == "error"
    assert details["api_access"] == "error"
    assert service_status.last_error_http_status is None
    assert (
        service_status.last_error_detail
        == "ProxBox backend could not connect to the configured Proxmox endpoint "
        "(pve.local:8006). Backend route: https://proxbox.local:8800/proxmox/version. "
        "Upstream error: HTTPConnectionPool(host='10.0.30.207', port=8000): Max "
        "retries exceeded with url: /proxmox/version?source=database&domain=pve.local "
        '(Caused by NewConnectionError("Failed to establish a new connection: '
        '[Errno 111] Connection refused"))'
    )


def test_proxmox_status_returns_sync_error_before_backend_version_call(
    monkeypatch,
    fastapi_endpoint,
    proxmox_endpoint,
):
    load_plugin_module(
        "netbox_proxbox.views.keepalive_status",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
        proxmox_endpoint=proxmox_endpoint,
    )
    ss = _service_status_module()

    monkeypatch.setattr(
        ss,
        "sync_proxmox_endpoint_to_backend",
        lambda *args, **kwargs: (False, "sync failed", 503),
    )

    calls = []

    def fake_get(url, verify=True, timeout=None, params=None, headers=None):
        calls.append(url)
        return ResponseStub([{"pve01": {"version": "8.3.0"}}])

    monkeypatch.setattr(ss.requests, "get", fake_get)

    service_status = ss.ServiceStatus()
    status, details = service_status.proxmox_status(
        1,
        "https://proxbox.local:8800",
        auth_headers={"Authorization": "Bearer backend-token"},
        backend_verify_ssl=True,
    )

    assert status == "error"
    assert details["api_access"] == "error"
    assert service_status.last_error_detail == "sync failed"
    assert service_status.last_error_http_status == 503
    assert calls == []


def test_get_service_status_unknown_service_returns_400(monkeypatch, fastapi_endpoint):
    module = load_plugin_module(
        "netbox_proxbox.views.keepalive_status",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
    )
    request = SimpleNamespace(
        user=SimpleNamespace(
            is_authenticated=True,
            has_perms=lambda *a, **k: True,
            has_perm=lambda *a, **k: True,
        ),
        method="GET",
    )
    resp = module.get_service_status_impl(request, "not-a-service", 1)
    assert resp.status_code == 400
    assert resp.payload["status"] == "error"
    assert "not-a-service" in resp.payload["detail"]
    assert "fastapi" in resp.payload["detail"]
