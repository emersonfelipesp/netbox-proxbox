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

    created_payloads = []

    class ValidationErrorResponse(ResponseStub):
        def raise_for_status(self):
            raise requests.exceptions.HTTPError("400")

    def fake_get(url, verify=True, timeout=None, headers=None):
        if url.endswith("/netbox/endpoint"):
            return ResponseStub([])
        if url.endswith("/netbox/status"):
            raise AssertionError("status check should not be reached")
        raise AssertionError(url)

    def fake_post(url, json, timeout=None, headers=None):
        created_payloads.append((url, json))
        return ValidationErrorResponse(
            {
                "detail": "token_key and token (secret) must both be set for NetBox API token v2"
            },
            status_code=400,
        )

    monkeypatch.setattr(module.requests, "get", fake_get)
    monkeypatch.setattr(module.requests, "post", fake_post)

    status = module.ServiceStatus().netbox_status(
        1,
        "https://proxbox.local:8800",
        auth_headers={"Authorization": "Bearer backend-token"},
    )
    assert status == "error"
    assert created_payloads[0][1]["token_version"] == "v2"
    assert "token" not in created_payloads[0][1]
    assert "token_key" not in created_payloads[0][1]


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
    requested = []

    def fake_get(url, verify=True, timeout=None):
        requested.append((url, verify))
        return ResponseStub([{"pve01": {"version": "8.3.0"}}])

    monkeypatch.setattr(module.requests, "get", fake_get)

    status = module.ServiceStatus().proxmox_status(1, "https://proxbox.local:8800")
    assert status == "success"
    assert requested == [
        ("https://proxbox.local:8800/proxmox/version?domain=pve.local", False)
    ]
