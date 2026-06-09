"""Tests for test_cards."""

from __future__ import annotations

import requests
import pytest

from tests.conftest import ResponseStub, _make_model_class, load_plugin_module


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
    monkeypatch.setattr(
        module,
        "resolve_backend_endpoint_id",
        lambda *args, **kwargs: (1, None),
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
            {"source": "database", "proxmox_endpoint_ids": "1"},
            {"Authorization": "Bearer backend-token"},
            True,
        ),
        (
            "https://proxbox.local:8800/proxmox/sessions",
            {"source": "database", "proxmox_endpoint_ids": "1"},
            {"Authorization": "Bearer backend-token"},
            True,
        ),
    ]


def test_get_proxmox_card_skips_disabled_endpoint_without_backend_calls(
    monkeypatch,
    fastapi_endpoint,
):
    proxmox_endpoint = type(
        "Obj",
        (),
        {
            "pk": 1,
            "id": 1,
            "name": "Disabled PVE",
            "domain": "pve.local",
            "ip_address": "10.0.30.9/24",
            "port": 8006,
            "enabled": False,
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
        lambda *args, **kwargs: pytest.fail("disabled endpoint was synced"),
    )
    monkeypatch.setattr(
        module,
        "resolve_backend_endpoint_id",
        lambda *args, **kwargs: pytest.fail("disabled endpoint was resolved"),
    )
    monkeypatch.setattr(
        module.requests,
        "get",
        lambda *args, **kwargs: pytest.fail("disabled endpoint made Proxmox GET"),
    )

    response = module.get_proxmox_card(None, 1)

    assert response.payload["cluster_data"] == {}
    assert "disabled" in response.payload["detail"]


def test_get_proxmox_card_uses_backend_endpoint_id_when_domain_is_empty(
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
    monkeypatch.setattr(
        module,
        "resolve_backend_endpoint_id",
        lambda *args, **kwargs: (2, None),
    )

    calls = []

    def fake_get(url, timeout=None, params=None, headers=None, verify=None):
        calls.append((url, params, headers, verify))
        return ResponseStub([])

    monkeypatch.setattr(module.requests, "get", fake_get)

    response = module.get_proxmox_card(None, 1)
    assert response.payload["cluster_data"] == {}
    assert calls[0][1] == {"source": "database", "proxmox_endpoint_ids": "2"}
    assert "domain" not in calls[0][1]
    assert "ip_address" not in calls[0][1]


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
    monkeypatch.setattr(
        module,
        "resolve_backend_endpoint_id",
        lambda *args, **kwargs: (1, None),
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
    monkeypatch.setattr(
        module,
        "resolve_backend_endpoint_id",
        lambda *args, **kwargs: (1, None),
    )

    def fake_get(url, timeout=None, params=None, headers=None, verify=None):
        raise requests.exceptions.ConnectionError(
            "HTTPConnectionPool(host='10.0.30.207', port=8000): Max retries exceeded "
            "with url: /proxmox/version?source=database&proxmox_endpoint_ids=1 "
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
        "retries exceeded with url: /proxmox/version?source=database&proxmox_endpoint_ids=1 "
        '(Caused by NewConnectionError("Failed to establish a new connection: '
        '[Errno 111] Connection refused"))'
    )


def test_get_proxmox_card_scopes_duplicate_domain_by_backend_id(
    monkeypatch,
    fastapi_endpoint,
):
    proxmox_endpoint = type(
        "Obj",
        (),
        {
            "pk": 2,
            "id": 2,
            "name": "PVE",
            "domain": "pve.local",
            "ip_address": "10.0.30.139/24",
            "port": 8006,
        },
    )()
    module = load_plugin_module(
        "netbox_proxbox.views.cards",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
        proxmox_endpoint=proxmox_endpoint,
    )
    module.ProxmoxEndpoint.objects = _make_model_class(
        "ProxmoxEndpoint",
        first=proxmox_endpoint,
        objects_by_pk={2: proxmox_endpoint},
    ).objects
    monkeypatch.setattr(
        module,
        "sync_proxmox_endpoint_to_backend",
        lambda *args, **kwargs: (True, None, None),
    )

    scoped_calls = []

    def fake_get(url, timeout=None, params=None, headers=None, verify=None):
        if url.endswith("/proxmox/endpoints"):
            return ResponseStub(
                [
                    {"id": 1, "name": "PVE (nb:1)", "domain": "pve.local"},
                    {"id": 2, "name": "PVE (nb:2)", "domain": "pve.local"},
                ]
            )
        if "/proxmox/version" in url:
            scoped_calls.append((url, params))
            return ResponseStub([{"PVE": {"version": "8.3.0"}}])
        if "/proxmox/sessions" in url:
            scoped_calls.append((url, params))
            return ResponseStub([{"name": "PVE", "mode": "cluster"}])
        raise AssertionError(url)

    monkeypatch.setattr(module.requests, "get", fake_get)

    response = module.get_proxmox_card(None, 2)

    assert response.payload["cluster_data"]["name"] == "PVE"
    assert scoped_calls == [
        (
            "https://proxbox.local:8800/proxmox/version",
            {"source": "database", "proxmox_endpoint_ids": "2"},
        ),
        (
            "https://proxbox.local:8800/proxmox/sessions",
            {"source": "database", "proxmox_endpoint_ids": "2"},
        ),
    ]
    for _, params in scoped_calls:
        assert "domain" not in params
        assert "ip_address" not in params


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
