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

    def fake_get(url, verify=True, timeout=None):
        if url.endswith("/netbox/endpoint"):
            endpoint_checks["count"] += 1
            if endpoint_checks["count"] == 1:
                return ResponseStub([])
            return ResponseStub([created_payloads[0][1]])
        if url.endswith("/netbox/status"):
            return ResponseStub({"status": "ok"})
        raise AssertionError(url)

    def fake_post(url, json, timeout=None):
        created_payloads.append((url, json))
        return ResponseStub({"id": 1})

    monkeypatch.setattr(module.requests, "get", fake_get)
    monkeypatch.setattr(module.requests, "post", fake_post)

    status = module.ServiceStatus().netbox_status(1, "https://proxbox.local:8800")
    assert status == "success"
    assert created_payloads[0][0].endswith("/netbox/endpoint")
    assert created_payloads[0][1]["token"] == "token-1"


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
