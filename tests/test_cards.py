"""Tests for test_cards."""

from __future__ import annotations

import requests

from tests.conftest import ResponseStub, load_plugin_module


def test_get_proxmox_card_merges_cluster_and_version_payloads(
    monkeypatch,
    fastapi_endpoint,
    proxmox_endpoint,
):
    module = load_plugin_module(
        "netbox_proxbox.views.cards",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
        proxmox_endpoint=proxmox_endpoint,
    )
    monkeypatch.setattr(
        module,
        "sync_proxmox_endpoint_to_backend",
        lambda *args, **kwargs: (True, None, None),
    )

    calls = []

    def fake_get(url, timeout=None, params=None, headers=None, verify=None):
        calls.append((url, params, headers, verify))
        if "/proxmox/version" in url:
            return ResponseStub([{"CLUSTER-A": {"version": "8.3.0", "release": "8.3"}}])
        if "/proxmox/sessions" in url:
            return ResponseStub(
                [
                    {
                        "domain": "10.0.0.30",
                        "http_port": 8006,
                        "user": "root@pam",
                        "name": "CLUSTER-A",
                        "mode": "cluster",
                    }
                ]
            )
        raise AssertionError(url)

    monkeypatch.setattr(module.requests, "get", fake_get)

    response = module.get_proxmox_card(None, 1)
    cluster_data = response.payload["cluster_data"]
    assert cluster_data["name"] == "CLUSTER-A"
    assert cluster_data["version"] == "8.3.0"
    assert response.payload["object"]["name"] == "pve01"
    assert calls == [
        (
            "https://proxbox.local:8800/proxmox/version",
            {"source": "database", "domain": "pve.local"},
            {"Authorization": "Bearer backend-token"},
            True,
        ),
        (
            "https://proxbox.local:8800/proxmox/sessions",
            {"source": "database", "domain": "pve.local"},
            {"Authorization": "Bearer backend-token"},
            True,
        ),
    ]


def test_get_proxmox_card_uses_ip_query_when_domain_is_empty(
    monkeypatch,
    fastapi_endpoint,
):
    proxmox_endpoint = type(
        "Obj",
        (),
        {
            "pk": 2,
            "name": "Proxmox Endpoint",
            "domain": "",
            "ip_address": "10.0.30.139/24",
        },
    )()
    module = load_plugin_module(
        "netbox_proxbox.views.cards",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
        proxmox_endpoint=proxmox_endpoint,
    )
    monkeypatch.setattr(
        module,
        "sync_proxmox_endpoint_to_backend",
        lambda *args, **kwargs: (True, None, None),
    )

    calls = []

    def fake_get(url, timeout=None, params=None, headers=None, verify=None):
        calls.append((url, params, headers, verify))
        return ResponseStub([])

    monkeypatch.setattr(module.requests, "get", fake_get)

    response = module.get_proxmox_card(None, 1)
    assert response.payload["cluster_data"] == {}
    assert calls[0][1] == {"source": "database", "ip_address": "10.0.30.139"}


def test_get_proxmox_card_returns_error_detail_on_backend_failure(
    monkeypatch,
    fastapi_endpoint,
    proxmox_endpoint,
):
    module = load_plugin_module(
        "netbox_proxbox.views.cards",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
        proxmox_endpoint=proxmox_endpoint,
    )
    monkeypatch.setattr(
        module,
        "sync_proxmox_endpoint_to_backend",
        lambda *args, **kwargs: (True, None, None),
    )

    class FailingResponse(ResponseStub):
        def __init__(self):
            super().__init__(payload={"detail": "No result found"}, status_code=404)
            self.text = '{"detail": "No result found"}'
            self.headers = {"Content-Type": "application/json"}

        def raise_for_status(self):
            err = requests.exceptions.HTTPError("HTTP 404")
            err.response = self
            raise err

    def fake_get(url, timeout=None, params=None, headers=None, verify=None):
        return FailingResponse()

    monkeypatch.setattr(module.requests, "get", fake_get)

    response = module.get_proxmox_card(None, 1)
    assert response.payload["cluster_data"] == {}
    assert response.payload["detail"] == "No result found"


def test_get_proxmox_card_normalizes_backend_connection_refused(
    monkeypatch,
    fastapi_endpoint,
    proxmox_endpoint,
):
    module = load_plugin_module(
        "netbox_proxbox.views.cards",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
        proxmox_endpoint=proxmox_endpoint,
    )
    monkeypatch.setattr(
        module,
        "sync_proxmox_endpoint_to_backend",
        lambda *args, **kwargs: (True, None, None),
    )

    def fake_get(url, timeout=None, params=None, headers=None, verify=None):
        raise requests.exceptions.ConnectionError(
            "HTTPConnectionPool(host='10.0.30.207', port=8000): Max retries exceeded "
            "with url: /proxmox/version?source=database&ip_address=10.0.30.9 "
            '(Caused by NewConnectionError("Failed to establish a new connection: '
            '[Errno 111] Connection refused"))'
        )

    monkeypatch.setattr(module.requests, "get", fake_get)

    response = module.get_proxmox_card(None, 1)
    assert response.payload["cluster_data"] == {}
    assert (
        response.payload["detail"]
        == "ProxBox backend could not connect to the configured Proxmox endpoint "
        "(pve.local:8006). Backend route: https://proxbox.local:8800/proxmox/version. "
        "Upstream error: HTTPConnectionPool(host='10.0.30.207', port=8000): Max "
        "retries exceeded with url: /proxmox/version?source=database&ip_address=10.0.30.9 "
        '(Caused by NewConnectionError("Failed to establish a new connection: '
        '[Errno 111] Connection refused"))'
    )


def test_get_proxmox_card_returns_sync_error_without_requesting_backend(
    monkeypatch,
    fastapi_endpoint,
    proxmox_endpoint,
):
    module = load_plugin_module(
        "netbox_proxbox.views.cards",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
        proxmox_endpoint=proxmox_endpoint,
    )
    monkeypatch.setattr(
        module,
        "sync_proxmox_endpoint_to_backend",
        lambda *args, **kwargs: (False, "sync failed", 502),
    )

    calls = []

    def fake_get(url, timeout=None, params=None, headers=None, verify=None):
        calls.append(url)
        return ResponseStub([])

    monkeypatch.setattr(module.requests, "get", fake_get)

    response = module.get_proxmox_card(None, 1)
    assert response.payload["cluster_data"] == {}
    assert response.payload["detail"] == "sync failed"
    assert response.payload["http_status"] == 502
    assert calls == []
