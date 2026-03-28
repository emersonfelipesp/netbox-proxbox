from __future__ import annotations

from types import SimpleNamespace

import requests

from tests.conftest import ResponseStub, load_plugin_module


def test_fastapi_status_falls_back_to_ip_after_ssl_error(
    monkeypatch,
    fastapi_endpoint,
):
    module = load_plugin_module(
        "netbox_proxbox.views.keepalive_status",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
    )
    calls = []

    def fake_get(url, verify=True, timeout=None):
        calls.append((url, verify))
        if "proxbox.local" in url:
            raise requests.exceptions.SSLError("bad cert")
        return ResponseStub({"ok": True})

    monkeypatch.setattr(module.requests, "get", fake_get)

    status = module.ServiceStatus().fastapi_status(1)
    assert status["connected"] is True
    assert status["connected_verify_ssl"] is False
    assert calls == [
        ("https://proxbox.local:8800", True),
        ("https://10.0.0.5:8800", False),
    ]


def test_netbox_status_creates_endpoint_and_checks_status(
    monkeypatch,
    fastapi_endpoint,
    netbox_endpoint,
):
    module = load_plugin_module(
        "netbox_proxbox.views.keepalive_status",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
        netbox_endpoint=netbox_endpoint,
    )
    monkeypatch.setattr(module.time, "sleep", lambda seconds: None)

    created_payloads = []
    endpoint_checks = {"count": 0}

    def fake_get(url, verify=True, timeout=None, headers=None):
        if url.endswith("/netbox/endpoint"):
            assert headers == {"Authorization": "Bearer backend-token"}
            endpoint_checks["count"] += 1
            if endpoint_checks["count"] == 1:
                return ResponseStub([])
            return ResponseStub([created_payloads[0][1]])
        if url.endswith("/netbox/status"):
            assert headers == {"Authorization": "Bearer backend-token"}
            return ResponseStub({"status": "ok"})
        raise AssertionError(url)

    def fake_post(url, json, timeout=None, headers=None):
        assert headers == {"Authorization": "Bearer backend-token"}
        created_payloads.append((url, json))
        return ResponseStub({"id": 1})

    monkeypatch.setattr(module.requests, "get", fake_get)
    monkeypatch.setattr(module.requests, "post", fake_post)

    status = module.ServiceStatus().netbox_status(
        1,
        "https://proxbox.local:8800",
        auth_headers={"Authorization": "Bearer backend-token"},
    )
    assert status == "success"
    assert created_payloads[0][0].endswith("/netbox/endpoint")
    assert created_payloads[0][1]["token"] == "token-1"
    assert created_payloads[0][1]["token_version"] == "v1"
    assert created_payloads[0][1]["domain"] == "netbox.local"


def test_netbox_status_v2_without_secret_fails_backend_validation(
    monkeypatch,
    fastapi_endpoint,
):
    netbox_endpoint = SimpleNamespace(
        id=1,
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
    module = load_plugin_module(
        "netbox_proxbox.views.keepalive_status",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
        netbox_endpoint=netbox_endpoint,
    )
    monkeypatch.setattr(module.time, "sleep", lambda seconds: None)

    service_status = module.ServiceStatus()
    status = service_status.netbox_status(
        1,
        "https://proxbox.local:8800",
        auth_headers={"Authorization": "Bearer backend-token"},
    )
    assert status == "error"
    assert service_status.last_error_detail == (
        "NetBox v2 credentials are incomplete. Provide both token key and token secret."
    )


def test_netbox_status_builds_full_v2_token_from_key_and_secret(
    monkeypatch,
    fastapi_endpoint,
):
    netbox_endpoint = SimpleNamespace(
        id=1,
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
    module = load_plugin_module(
        "netbox_proxbox.views.keepalive_status",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
        netbox_endpoint=netbox_endpoint,
    )
    monkeypatch.setattr(module.time, "sleep", lambda seconds: None)

    created_payloads = []

    def fake_get(url, verify=True, timeout=None, headers=None):
        if url.endswith("/netbox/endpoint"):
            return ResponseStub([])
        if url.endswith("/netbox/status"):
            return ResponseStub({"status": "ok"})
        raise AssertionError(url)

    def fake_post(url, json, timeout=None, headers=None):
        created_payloads.append((url, json))
        return ResponseStub({"id": 1})

    monkeypatch.setattr(module.requests, "get", fake_get)
    monkeypatch.setattr(module.requests, "post", fake_post)

    status = module.ServiceStatus().netbox_status(
        1,
        "https://proxbox.local:8800",
        auth_headers={"Authorization": "Bearer backend-token"},
    )
    assert status == "success"
    assert created_payloads[0][1]["token"] == "v2-token-secret"
    assert created_payloads[0][1]["token_version"] == "v2"
    assert created_payloads[0][1]["token_key"] == "v2-token-key"
    assert created_payloads[0][1]["ip_address"] == "10.0.0.20"
    assert created_payloads[0][1]["domain"] == "10.0.0.20"


def test_backend_auth_headers_accepts_prefixed_and_bare_tokens(
    monkeypatch,
    fastapi_endpoint,
):
    module = load_plugin_module(
        "netbox_proxbox.views.keepalive_status",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
    )

    assert module.ServiceStatus._backend_auth_headers(None) == {}
    assert module.ServiceStatus._backend_auth_headers(SimpleNamespace(token="")) == {}
    assert module.ServiceStatus._backend_auth_headers(
        SimpleNamespace(token="Bearer abc")
    ) == {"Authorization": "Bearer abc"}
    assert module.ServiceStatus._backend_auth_headers(
        SimpleNamespace(token="Token abc")
    ) == {"Authorization": "Token abc"}
    assert module.ServiceStatus._backend_auth_headers(SimpleNamespace(token="abc")) == {
        "Authorization": "Bearer abc"
    }


def test_netbox_status_exposes_error_detail_on_backend_failure(
    monkeypatch,
    fastapi_endpoint,
    netbox_endpoint,
):
    module = load_plugin_module(
        "netbox_proxbox.views.keepalive_status",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
        netbox_endpoint=netbox_endpoint,
    )
    monkeypatch.setattr(module.time, "sleep", lambda seconds: None)

    class FailingResponse(ResponseStub):
        text = '{"detail": "token is required for NetBox API token v1", "python_exception": "ValidationError"}'

        def raise_for_status(self):
            err = requests.exceptions.HTTPError("400")
            err.response = self
            raise err

    def fake_get(url, verify=True, timeout=None, headers=None):
        if url.endswith("/netbox/endpoint"):
            return ResponseStub([])
        raise AssertionError(url)

    def fake_post(url, json, timeout=None, headers=None):
        return FailingResponse(
            {
                "detail": "token is required for NetBox API token v1",
                "python_exception": "ValidationError",
            },
            status_code=400,
        )

    monkeypatch.setattr(module.requests, "get", fake_get)
    monkeypatch.setattr(module.requests, "post", fake_post)

    service_status = module.ServiceStatus()
    status = service_status.netbox_status(
        1,
        "https://proxbox.local:8800",
        auth_headers={"Authorization": "Bearer backend-token"},
    )

    assert status == "error"
    assert "token is required for NetBox API token v1" in (
        service_status.last_error_detail or ""
    )
    assert service_status.last_error_http_status == 400


def test_extract_error_detail_identifies_html_404_from_wrong_backend_target(
    monkeypatch,
    fastapi_endpoint,
):
    module = load_plugin_module(
        "netbox_proxbox.views.keepalive_status",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
    )

    class Html404Response(ResponseStub):
        def __init__(self):
            super().__init__(payload={}, status_code=404)
            self.text = "<!DOCTYPE html><html><body>Page Not Found</body></html>"
            self.headers = {"Content-Type": "text/html; charset=utf-8"}
            self.url = "http://10.0.30.206:8000/netbox/endpoint"

    err = requests.exceptions.HTTPError("404")
    err.response = Html404Response()

    detail, status = module.ServiceStatus._extract_error_detail(err)

    assert status == 404
    assert "Backend returned HTML instead of ProxBox API JSON" in detail
    assert "pointing to NetBox UI instead of proxbox-api" in detail


def test_proxmox_status_uses_domain_query_when_available(
    monkeypatch,
    fastapi_endpoint,
    proxmox_endpoint,
):
    module = load_plugin_module(
        "netbox_proxbox.views.keepalive_status",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
        proxmox_endpoint=proxmox_endpoint,
    )
    monkeypatch.setattr(module.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(
        module,
        "sync_proxmox_endpoint_to_backend",
        lambda *args, **kwargs: (True, None, None),
    )
    requested = []

    def fake_get(url, verify=True, timeout=None, params=None, headers=None):
        requested.append((url, params, headers, verify))
        return ResponseStub([{"pve01": {"version": "8.3.0"}}])

    monkeypatch.setattr(module.requests, "get", fake_get)

    status = module.ServiceStatus().proxmox_status(
        1,
        "https://proxbox.local:8800",
        auth_headers={"Authorization": "Bearer backend-token"},
        backend_verify_ssl=True,
    )
    assert status == "success"
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
    module = load_plugin_module(
        "netbox_proxbox.views.keepalive_status",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
        proxmox_endpoint=proxmox_endpoint,
    )
    monkeypatch.setattr(
        module,
        "sync_proxmox_endpoint_to_backend",
        lambda *args, **kwargs: (True, None, None),
    )
    requested = []

    def fake_get(url, verify=True, timeout=None, params=None, headers=None):
        requested.append((url, params, headers, verify))
        return ResponseStub([{"pve01": {"version": "8.3.0"}}])

    monkeypatch.setattr(module.requests, "get", fake_get)

    status = module.ServiceStatus().proxmox_status(
        1,
        "https://proxbox.local:8800",
        auth_headers={"Authorization": "Bearer backend-token"},
        backend_verify_ssl=False,
    )
    assert status == "success"
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
    module = load_plugin_module(
        "netbox_proxbox.views.keepalive_status",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
        proxmox_endpoint=proxmox_endpoint,
    )
    monkeypatch.setattr(module.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(
        module,
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

    monkeypatch.setattr(module.requests, "get", fake_get)

    service_status = module.ServiceStatus()
    status = service_status.proxmox_status(
        1,
        "https://proxbox.local:8800",
        auth_headers={"Authorization": "Bearer backend-token"},
        backend_verify_ssl=True,
    )

    assert status == "error"
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
    module = load_plugin_module(
        "netbox_proxbox.views.keepalive_status",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
        proxmox_endpoint=proxmox_endpoint,
    )

    monkeypatch.setattr(
        module,
        "sync_proxmox_endpoint_to_backend",
        lambda *args, **kwargs: (False, "sync failed", 503),
    )

    calls = []

    def fake_get(url, verify=True, timeout=None, params=None, headers=None):
        calls.append(url)
        return ResponseStub([{"pve01": {"version": "8.3.0"}}])

    monkeypatch.setattr(module.requests, "get", fake_get)

    service_status = module.ServiceStatus()
    status = service_status.proxmox_status(
        1,
        "https://proxbox.local:8800",
        auth_headers={"Authorization": "Bearer backend-token"},
        backend_verify_ssl=True,
    )

    assert status == "error"
    assert service_status.last_error_detail == "sync failed"
    assert service_status.last_error_http_status == 503
    assert calls == []
