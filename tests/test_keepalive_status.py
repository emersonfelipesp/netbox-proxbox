"""Tests for test_keepalive_status."""

from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import requests
import pytest

from tests.conftest import ResponseStub, _make_model_class, load_plugin_module


REPO_ROOT = Path(__file__).resolve().parents[1]


def _service_status_module():
    return importlib.import_module("netbox_proxbox.services.service_status")


def _backend_proxy_module():
    """Return the module that actually owns ``request_backend_json``.

    ``service_status`` imports it *lazily inside the function body* to break a
    circular import, so it is not an attribute of ``service_status`` and cannot
    be monkeypatched there -- patches must target the defining module.
    """
    return importlib.import_module("netbox_proxbox.services.backend_proxy")


def _install_pbs_server_stub(monkeypatch, pbs_server):
    netbox_pbs_module = types.ModuleType("netbox_pbs")
    models_module = types.ModuleType("netbox_pbs.models")
    models_module.PBSServer = _make_model_class(
        "PBSServer",
        first=pbs_server,
        objects_by_pk={getattr(pbs_server, "pk", 1): pbs_server},
    )
    netbox_pbs_module.models = models_module
    monkeypatch.setitem(sys.modules, "netbox_pbs", netbox_pbs_module)
    monkeypatch.setitem(sys.modules, "netbox_pbs.models", models_module)


def _keepalive_request():
    return SimpleNamespace(
        user=SimpleNamespace(
            is_authenticated=True,
            has_perms=lambda *a, **k: True,
            has_perm=lambda *a, **k: True,
        ),
        method="GET",
    )


class _RecordingProxmoxEndpointManager:
    def __init__(self, endpoint):
        self.endpoint = endpoint
        self.filters = []
        self.updates = []

    def get(self, *args, **kwargs):
        return self.endpoint

    def filter(self, *args, **kwargs):
        self.filters.append(kwargs)
        return self

    def update(self, **kwargs):
        self.updates.append(kwargs)
        return 1


def _pbs_server(*, enabled=True):
    return SimpleNamespace(
        id=7,
        pk=7,
        name="PBS01",
        host="10.0.30.134",
        port=8007,
        verify_ssl=True,
        enabled=enabled,
    )


def _patch_backend_and_pbs_status(monkeypatch, ss, status_payload):
    def fake_get(
        url, verify=True, timeout=None, params=None, headers=None, allow_redirects=True
    ):
        if url == "https://proxbox.local:8800":
            return ResponseStub({"ok": True})
        if url.endswith("/version"):
            return ResponseStub({"version": "0.0.15"})
        if url.endswith("/pbs/status"):
            return ResponseStub(status_payload)
        raise AssertionError(url)

    monkeypatch.setattr(ss.requests, "get", fake_get)


def test_fastapi_status_falls_back_to_ip_after_ssl_error(
    monkeypatch,
    fastapi_endpoint,
):
    fastapi_endpoint.verify_ssl = False
    load_plugin_module(
        "netbox_proxbox.views.keepalive_status",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
        get_fastapi_url=lambda obj: {
            "http_url": "https://proxbox.local:8800",
            "ip_address_url": "https://10.0.0.5:8800",
            "verify_ssl": False,
            "websocket_url": "wss://proxbox.local:8801/ws",
        },
    )
    ss = _service_status_module()
    calls = []

    def fake_get(url, verify=True, timeout=None, headers=None):
        calls.append((url, verify, headers))
        if "proxbox.local" in url:
            raise requests.exceptions.SSLError("bad cert")
        if url.endswith("/version"):
            return ResponseStub({"version": "0.0.15"})
        return ResponseStub({"ok": True})

    monkeypatch.setattr(ss.requests, "get", fake_get)

    status = ss.ServiceStatus().fastapi_status(1)
    assert status["connected"] is True
    assert status["connected_verify_ssl"] is False
    assert status["backend_version"] == "0.0.15"
    assert calls == [
        ("https://proxbox.local:8800", False, None),
        ("https://10.0.0.5:8800", False, None),
        (
            "https://10.0.0.5:8800/version",
            False,
            {"Authorization": "Bearer backend-token"},
        ),
    ]


def test_fastapi_status_does_not_retry_insecurely_when_verify_ssl_enabled(
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

    def fake_get(url, verify=True, timeout=None, headers=None):
        calls.append((url, verify, headers))
        if "proxbox.local" in url:
            raise requests.exceptions.SSLError("bad cert")
        raise AssertionError("verify_ssl=True must not retry with verify=False")

    monkeypatch.setattr(ss.requests, "get", fake_get)

    status = ss.ServiceStatus().fastapi_status(1)
    assert status["connected"] is False
    assert status["api_access"] == "error"
    assert "FastAPI URL check failed" in status["detail"]
    assert calls == [("https://proxbox.local:8800", True, None)]


def test_fastapi_status_rejected_selected_key_stops_all_authenticated_requests(
    monkeypatch,
    fastapi_endpoint,
):
    load_plugin_module(
        "netbox_proxbox.views.keepalive_status",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
    )
    ss = _service_status_module()
    auth = sys.modules["netbox_proxbox.services.backend_auth"]
    key_checks: list[int | None] = []

    def reject_key(*, endpoint_id=None):
        key_checks.append(endpoint_id)
        return False, "candidate rejected"

    monkeypatch.setattr(auth, "ensure_backend_key_registered", reject_key)
    calls = []

    def fake_get(url, verify=True, timeout=None, headers=None):
        calls.append((url, headers))
        if url.endswith("/version"):
            raise AssertionError("version probe ran after key rejection")
        return ResponseStub({"ok": True})

    monkeypatch.setattr(ss.requests, "get", fake_get)

    status = ss.ServiceStatus().fastapi_status(1)

    assert key_checks == [1]
    assert calls == [("https://proxbox.local:8800", None)]
    assert status["connected"] is True
    assert status["authentication"] == "error"
    assert status["api_access"] == "error"
    assert status["backend_version"] is None
    assert "preflight failed" in status["detail"]


def test_fastapi_status_disabled_endpoint_does_not_connect(
    monkeypatch,
    fastapi_endpoint,
):
    fastapi_endpoint.enabled = False
    load_plugin_module(
        "netbox_proxbox.views.keepalive_status",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
    )
    ss = _service_status_module()

    def fail_get(*args, **kwargs):
        raise AssertionError("disabled FastAPI endpoint attempted network access")

    monkeypatch.setattr(ss.requests, "get", fail_get)

    status = ss.ServiceStatus().fastapi_status(1)

    assert status["connected"] is False
    assert status["api_access"] == "error"
    assert "disabled" in status["detail"]


def test_fastapi_status_warns_for_agent_kv_affected_backend(
    monkeypatch,
    fastapi_endpoint,
):
    load_plugin_module(
        "netbox_proxbox.views.keepalive_status",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
    )
    ss = _service_status_module()

    def fake_get(url, verify=True, timeout=None, headers=None):
        if url.endswith("/version"):
            return ResponseStub({"version": "0.0.14"})
        return ResponseStub({"ok": True})

    monkeypatch.setattr(ss.requests, "get", fake_get)

    status = ss.ServiceStatus().fastapi_status(1)

    assert status["connected"] is True
    assert status["api_access"] == "success"
    assert status["backend_version"] == "0.0.14"
    assert len(status["warnings"]) == 1
    assert "PR #156" in status["warnings"][0]


def test_fastapi_status_errors_for_backend_before_vm_ip_config_fix(
    monkeypatch,
    fastapi_endpoint,
):
    load_plugin_module(
        "netbox_proxbox.views.keepalive_status",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
    )
    ss = _service_status_module()

    def fake_get(url, verify=True, timeout=None, headers=None):
        if url.endswith("/version"):
            return ResponseStub({"version": "0.0.12"})
        return ResponseStub({"ok": True})

    monkeypatch.setattr(ss.requests, "get", fake_get)

    status = ss.ServiceStatus().fastapi_status(1)

    assert status["connected"] is True
    assert status["api_access"] == "error"
    assert status["backend_version"] == "0.0.12"
    assert "too old for reliable VM IP sync" in status["detail"]


def test_fastapi_keepalive_payload_exposes_backend_version_warning(
    monkeypatch,
    fastapi_endpoint,
):
    module = load_plugin_module(
        "netbox_proxbox.views.keepalive_status",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
    )
    ss = _service_status_module()

    def fake_get(url, verify=True, timeout=None, headers=None):
        if url.endswith("/version"):
            return ResponseStub({"version": "0.0.14"})
        return ResponseStub({"ok": True})

    monkeypatch.setattr(ss.requests, "get", fake_get)

    request = SimpleNamespace(
        user=SimpleNamespace(
            is_authenticated=True,
            has_perms=lambda *a, **k: True,
            has_perm=lambda *a, **k: True,
        ),
        method="GET",
    )

    response = module.get_service_status_impl(request, "fastapi", 1)

    assert response.payload["status"] == "success"
    assert response.payload["backend_version"] == "0.0.14"
    assert len(response.payload["warnings"]) == 1
    assert "PR #156" in response.payload["detail"]


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
        'with url: / (Caused by NewConnectionError("Failed to establish a new '
        'connection: [Errno 111] Connection refused"))'
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


def test_proxmox_status_uses_backend_endpoint_id_query_when_domain_available(
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
    monkeypatch.setattr(
        ss,
        "resolve_backend_endpoint_id",
        lambda *args, **kwargs: (11, None),
    )
    monkeypatch.setattr(ss, "_last_proxmox_mode_check", {})
    requested = []

    def fake_get(
        url, verify=True, timeout=None, params=None, headers=None, allow_redirects=True
    ):
        requested.append((url, params, headers, verify))
        if url.endswith("/proxmox/cluster/status"):
            return ResponseStub([{"type": "node", "name": "pve01"}])
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
            {"source": "database", "proxmox_endpoint_ids": "11"},
            {"Authorization": "Bearer backend-token"},
            True,
        ),
        (
            "https://proxbox.local:8800/proxmox/cluster/status",
            {"source": "database", "proxmox_endpoint_ids": "11"},
            {"Authorization": "Bearer backend-token"},
            True,
        ),
    ]


def test_proxmox_status_skips_disabled_endpoint_without_backend_calls(
    monkeypatch,
    fastapi_endpoint,
):
    proxmox_endpoint = SimpleNamespace(
        id=1,
        pk=1,
        name="Disabled PVE",
        domain="pve.local",
        ip_address="10.0.30.9/24",
        port=8006,
        verify_ssl=False,
        enabled=False,
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
        lambda *args, **kwargs: pytest.fail("disabled endpoint was synced"),
    )
    monkeypatch.setattr(
        ss,
        "resolve_backend_endpoint_id",
        lambda *args, **kwargs: pytest.fail("disabled endpoint was resolved"),
    )
    monkeypatch.setattr(
        ss.requests,
        "get",
        lambda *args, **kwargs: pytest.fail("disabled endpoint made Proxmox GET"),
    )

    status, details = ss.ServiceStatus().proxmox_status(
        1,
        "https://proxbox.local:8800",
        auth_headers={"Authorization": "Bearer backend-token"},
        backend_verify_ssl=True,
    )

    assert status == "disabled"
    assert details["api_access"] == "disabled"
    assert "disabled" in details["detail"]


def test_proxmox_status_uses_backend_endpoint_id_query_when_domain_missing(
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
    monkeypatch.setattr(
        ss,
        "resolve_backend_endpoint_id",
        lambda *args, **kwargs: (12, None),
    )
    monkeypatch.setattr(ss, "_last_proxmox_mode_check", {})
    requested = []

    def fake_get(
        url, verify=True, timeout=None, params=None, headers=None, allow_redirects=True
    ):
        requested.append((url, params, headers, verify))
        if url.endswith("/proxmox/cluster/status"):
            return ResponseStub([{"type": "node", "name": "pve01"}])
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
            {"source": "database", "proxmox_endpoint_ids": "12"},
            {"Authorization": "Bearer backend-token"},
            False,
        ),
        (
            "https://proxbox.local:8800/proxmox/cluster/status",
            {"source": "database", "proxmox_endpoint_ids": "12"},
            {"Authorization": "Bearer backend-token"},
            False,
        ),
    ]


def test_proxmox_status_scopes_duplicate_domain_by_backend_id(
    monkeypatch,
    fastapi_endpoint,
):
    proxmox_endpoint = SimpleNamespace(
        id=2,
        pk=2,
        name="PVE",
        domain="pve.local",
        ip_address="10.0.0.31/24",
        port=8006,
        verify_ssl=False,
        mode="undefined",
    )
    load_plugin_module(
        "netbox_proxbox.views.keepalive_status",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
        proxmox_endpoint=proxmox_endpoint,
    )
    ss = _service_status_module()
    ss.ProxmoxEndpoint.objects = _make_model_class(
        "ProxmoxEndpoint",
        first=proxmox_endpoint,
        objects_by_pk={2: proxmox_endpoint},
    ).objects
    monkeypatch.setattr(ss.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(
        ss,
        "sync_proxmox_endpoint_to_backend",
        lambda *args, **kwargs: (True, None, None),
    )
    monkeypatch.setattr(ss, "_last_proxmox_mode_check", {})
    scoped_calls = []

    def fake_get(
        url, verify=True, timeout=None, params=None, headers=None, allow_redirects=True
    ):
        if url.endswith("/proxmox/endpoints"):
            # Same domain on both rows is the point of this test; `port` is
            # present because the resolver confirms the located row still dials
            # `(host, port)` and refuses a row it cannot resolve one from.
            return ResponseStub(
                [
                    {
                        "id": 1,
                        "name": "PVE (nb:1)",
                        "domain": "pve.local",
                        "port": 8006,
                    },
                    {
                        "id": 2,
                        "name": "PVE (nb:2)",
                        "domain": "pve.local",
                        "port": 8006,
                    },
                ]
            )
        if url.endswith("/proxmox/version"):
            scoped_calls.append((url, params))
            return ResponseStub([{"PVE": {"version": "8.3.0"}}])
        if url.endswith("/proxmox/cluster/status"):
            scoped_calls.append((url, params))
            return ResponseStub([{"type": "node", "name": "pve01"}])
        raise AssertionError(url)

    monkeypatch.setattr(ss.requests, "get", fake_get)

    status, details = ss.ServiceStatus().proxmox_status(
        2,
        "https://proxbox.local:8800",
        auth_headers={"Authorization": "Bearer backend-token"},
        backend_verify_ssl=True,
    )

    assert status == "success"
    assert details["api_access"] == "success"
    assert scoped_calls == [
        (
            "https://proxbox.local:8800/proxmox/version",
            {"source": "database", "proxmox_endpoint_ids": "2"},
        ),
        (
            "https://proxbox.local:8800/proxmox/cluster/status",
            {"source": "database", "proxmox_endpoint_ids": "2"},
        ),
    ]
    for _, params in scoped_calls:
        assert "domain" not in params
        assert "ip_address" not in params


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
    monkeypatch.setattr(
        ss,
        "resolve_backend_endpoint_id",
        lambda *args, **kwargs: (1, None),
    )

    def fake_get(
        url, verify=True, timeout=None, params=None, headers=None, allow_redirects=True
    ):
        raise requests.exceptions.ConnectionError(
            "HTTPConnectionPool(host='10.0.30.207', port=8000): Max retries exceeded "
            "with url: /proxmox/version?source=database&proxmox_endpoint_ids=1 "
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
        # Class-only tail: the rendered exception can echo request content and
        # the text sweep is pattern-based, so only the class name may leave.
        "Upstream error: ConnectionError"
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

    def fake_get(
        url, verify=True, timeout=None, params=None, headers=None, allow_redirects=True
    ):
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


def test_pbs_keepalive_uses_backend_status_host_fallback(
    monkeypatch,
    fastapi_endpoint,
):
    module = load_plugin_module(
        "netbox_proxbox.views.keepalive_status",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
    )
    pbs_server = _pbs_server()
    _install_pbs_server_stub(monkeypatch, pbs_server)
    ss = _service_status_module()
    _patch_backend_and_pbs_status(
        monkeypatch,
        ss,
        {
            "items": [
                {
                    "endpoint_id": 99,
                    "name": "Backend PBS",
                    "host": "10.0.30.134",
                    "port": 8007,
                    "reachable": True,
                    "version": "3.3.2",
                }
            ]
        },
    )

    response = module.get_service_status_impl(_keepalive_request(), "pbs", 7)

    assert response.status_code == 200
    assert response.payload["status"] == "success"
    assert response.payload["target_address"] == "10.0.30.134"
    assert response.payload["target_port"] == 8007
    assert response.payload["authentication"] == "success"
    assert response.payload["api_access"] == "success"


def test_netbox_keepalive_disabled_endpoint_returns_before_backend_check(
    monkeypatch,
    fastapi_endpoint,
    netbox_endpoint,
):
    netbox_endpoint.enabled = False
    module = load_plugin_module(
        "netbox_proxbox.views.keepalive_status",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
        netbox_endpoint=netbox_endpoint,
    )
    ss = _service_status_module()

    def fail_get(*args, **kwargs):
        raise AssertionError("disabled NetBox keepalive attempted network access")

    monkeypatch.setattr(ss.requests, "get", fail_get)

    response = module.get_service_status_impl(_keepalive_request(), "netbox", 1)

    assert response.status_code == 200
    assert response.payload["status"] == "error"
    assert "disabled" in response.payload["detail"]


def test_proxmox_keepalive_disabled_endpoint_returns_disabled_before_backend_check(
    monkeypatch,
    fastapi_endpoint,
):
    proxmox_endpoint = SimpleNamespace(
        id=1,
        pk=1,
        name="Disabled PVE",
        domain="pve.local",
        ip_address="10.0.30.9/24",
        port=8006,
        verify_ssl=False,
        enabled=False,
    )
    module = load_plugin_module(
        "netbox_proxbox.views.keepalive_status",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
        proxmox_endpoint=proxmox_endpoint,
    )
    ss = _service_status_module()

    def fail_get(*args, **kwargs):
        raise AssertionError("disabled Proxmox keepalive attempted network access")

    monkeypatch.setattr(ss.requests, "get", fail_get)

    response = module.get_service_status_impl(_keepalive_request(), "proxmox", 1)

    assert response.status_code == 200
    assert response.payload["status"] == "disabled"
    assert response.payload["target_address"] == "pve.local"
    assert response.payload["target_port"] == 8006
    assert response.payload["authentication"] == "disabled"
    assert response.payload["api_access"] == "disabled"
    assert "disabled" in response.payload["detail"]


def test_pbs_keepalive_disabled_endpoint_returns_before_backend_check(
    monkeypatch,
    fastapi_endpoint,
):
    module = load_plugin_module(
        "netbox_proxbox.views.keepalive_status",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
    )
    pbs_server = _pbs_server(enabled=False)
    _install_pbs_server_stub(monkeypatch, pbs_server)
    ss = _service_status_module()

    def fail_get(*args, **kwargs):
        raise AssertionError("disabled PBS keepalive attempted network access")

    monkeypatch.setattr(ss.requests, "get", fail_get)

    response = module.get_service_status_impl(_keepalive_request(), "pbs", 7)

    assert response.status_code == 200
    assert response.payload["status"] == "error"
    assert "disabled" in response.payload["detail"]


def test_pbs_status_disabled_endpoint_does_not_request_backend(monkeypatch):
    ss = _service_status_module()
    pbs_server = _pbs_server(enabled=False)

    def fail_get(*args, **kwargs):
        raise AssertionError("disabled PBS status attempted backend access")

    monkeypatch.setattr(ss.requests, "get", fail_get)

    status, details = ss.ServiceStatus().pbs_status(
        endpoint=pbs_server,
        base_url="https://proxbox.local:8800",
        auth_headers={"Authorization": "Bearer backend-token"},
    )

    assert status == "error"
    assert details["target_address"] == "10.0.30.134"
    assert details["target_port"] == 8007
    assert "disabled" in details["detail"]


def test_pbs_keepalive_reports_unreachable_reason(
    monkeypatch,
    fastapi_endpoint,
):
    module = load_plugin_module(
        "netbox_proxbox.views.keepalive_status",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
    )
    pbs_server = _pbs_server()
    _install_pbs_server_stub(monkeypatch, pbs_server)
    ss = _service_status_module()
    _patch_backend_and_pbs_status(
        monkeypatch,
        ss,
        {
            "items": [
                {
                    "endpoint_id": 7,
                    "name": "PBS01",
                    "host": "10.0.30.134",
                    "port": 8007,
                    "reachable": False,
                    "reason": "Token rejected",
                }
            ]
        },
    )

    response = module.get_service_status_impl(_keepalive_request(), "pbs", 7)

    assert response.status_code == 200
    assert response.payload["status"] == "error"
    assert response.payload["authentication"] == "success"
    assert response.payload["api_access"] == "error"
    assert response.payload["detail"] == "Token rejected"


def test_pbs_keepalive_reports_missing_backend_match(
    monkeypatch,
    fastapi_endpoint,
):
    module = load_plugin_module(
        "netbox_proxbox.views.keepalive_status",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
    )
    pbs_server = _pbs_server()
    _install_pbs_server_stub(monkeypatch, pbs_server)
    ss = _service_status_module()
    _patch_backend_and_pbs_status(
        monkeypatch,
        ss,
        {
            "items": [
                {
                    "endpoint_id": 42,
                    "name": "Other PBS",
                    "host": "10.0.30.200",
                    "port": 8007,
                    "reachable": True,
                }
            ]
        },
    )

    response = module.get_service_status_impl(_keepalive_request(), "pbs", 7)

    assert response.status_code == 200
    assert response.payload["status"] == "error"
    assert "PBS status for PBS01 was not returned" in response.payload["detail"]


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
    assert "pbs" in resp.payload["detail"]


def test_proxmox_mode_derivation_is_shared_by_keepalive_and_full_sync(
    monkeypatch,
    fastapi_endpoint,
):
    load_plugin_module(
        "netbox_proxbox.views.keepalive_status",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
    )
    from netbox_proxbox.services.proxmox_mode import derive_proxmox_endpoint_mode

    mode = derive_proxmox_endpoint_mode(
        SimpleNamespace(name="pve-cluster", quorate=True),
        [SimpleNamespace(name="pve01")],
    )

    assert mode == "standalone"
    assert (
        "derive_proxmox_endpoint_mode("
        in (REPO_ROOT / "netbox_proxbox/services/service_status.py").read_text()
    )
    assert (
        "derive_proxmox_endpoint_mode("
        in (REPO_ROOT / "netbox_proxbox/services/sync_cluster.py").read_text()
    )


def test_proxmox_keepalive_mode_write_uses_queryset_update_not_save():
    source = (REPO_ROOT / "netbox_proxbox/services/service_status.py").read_text()

    assert "ProxmoxEndpoint.objects.filter(pk=pk).update(mode=mode)" in source
    assert 'endpoint.save(update_fields=["mode"])' not in source


def test_proxmox_mode_detected_on_successful_keepalive(
    monkeypatch,
    fastapi_endpoint,
):
    """Keepalive sets endpoint.mode to 'cluster' when cluster/status returns topology."""
    proxmox_endpoint = SimpleNamespace(
        id=1,
        pk=1,
        name="pve01",
        domain="pve.local",
        ip_address="10.0.0.30/24",
        port=8006,
        verify_ssl=False,
        mode="undefined",
        save=lambda update_fields=None: pytest.fail("keepalive must not call save()"),
    )
    load_plugin_module(
        "netbox_proxbox.views.keepalive_status",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
        proxmox_endpoint=proxmox_endpoint,
    )
    ss = _service_status_module()
    endpoint_manager = _RecordingProxmoxEndpointManager(proxmox_endpoint)
    monkeypatch.setattr(ss.ProxmoxEndpoint, "objects", endpoint_manager)
    monkeypatch.setattr(ss.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(
        ss,
        "sync_proxmox_endpoint_to_backend",
        lambda *args, **kwargs: (True, None, None),
    )
    monkeypatch.setattr(
        ss,
        "resolve_backend_endpoint_id",
        lambda *args, **kwargs: (1, None),
    )
    monkeypatch.setattr(ss, "_last_proxmox_mode_check", {})

    def fake_get(
        url, verify=True, timeout=None, params=None, headers=None, allow_redirects=True
    ):
        if url.endswith("/proxmox/cluster/status"):
            return ResponseStub(
                [
                    {"type": "cluster", "name": "pve-cluster"},
                    {"type": "node", "name": "pve01"},
                    {"type": "node", "name": "pve02"},
                ]
            )
        return ResponseStub([{"pve01": {"version": "8.3.0"}}])

    monkeypatch.setattr(ss.requests, "get", fake_get)

    status, details = ss.ServiceStatus().proxmox_status(
        1,
        "https://proxbox.local:8800",
        auth_headers={"Authorization": "Bearer backend-token"},
        backend_verify_ssl=False,
    )

    assert status == "success"
    assert proxmox_endpoint.mode == "cluster"
    assert endpoint_manager.filters == [{"pk": 1}]
    assert endpoint_manager.updates == [{"mode": "cluster"}]


def test_proxmox_mode_detects_named_single_node_cluster_as_standalone(
    monkeypatch,
    fastapi_endpoint,
):
    proxmox_endpoint = SimpleNamespace(
        id=1,
        pk=1,
        name="pve01",
        domain="pve.local",
        ip_address="10.0.0.30/24",
        port=8006,
        verify_ssl=False,
        mode="undefined",
        save=lambda update_fields=None: pytest.fail("keepalive must not call save()"),
    )
    load_plugin_module(
        "netbox_proxbox.views.keepalive_status",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
        proxmox_endpoint=proxmox_endpoint,
    )
    ss = _service_status_module()
    endpoint_manager = _RecordingProxmoxEndpointManager(proxmox_endpoint)
    monkeypatch.setattr(ss.ProxmoxEndpoint, "objects", endpoint_manager)
    monkeypatch.setattr(ss.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(
        ss,
        "sync_proxmox_endpoint_to_backend",
        lambda *args, **kwargs: (True, None, None),
    )
    monkeypatch.setattr(
        ss,
        "resolve_backend_endpoint_id",
        lambda *args, **kwargs: (1, None),
    )
    monkeypatch.setattr(ss, "_last_proxmox_mode_check", {})

    def fake_get(
        url, verify=True, timeout=None, params=None, headers=None, allow_redirects=True
    ):
        assert url.endswith("/proxmox/version")
        return ResponseStub([{"pve01": {"version": "8.3.0"}}])

    def fake_request_backend_json(
        context,
        path,
        *,
        query_params=None,
        timeout=5,
        endpoint_id=None,
        method="GET",
    ):
        assert context.http_url == "https://proxbox.local:8800"
        assert context.verify_ssl is False
        assert context.headers == {"Authorization": "Bearer backend-token"}
        assert path == "proxmox/cluster/status"
        assert query_params == {
            "source": "database",
            "proxmox_endpoint_ids": "1",
        }
        assert timeout == 10
        assert endpoint_id is None
        assert method == "GET"
        return {
            "ok": True,
            "response": [
                {
                    "type": "cluster",
                    "name": "pve-cluster",
                    "quorate": 1,
                    "node_list": [{"type": "node", "name": "pve01"}],
                }
            ],
        }, 200

    monkeypatch.setattr(ss.requests, "get", fake_get)
    monkeypatch.setattr(
        _backend_proxy_module(), "request_backend_json", fake_request_backend_json
    )

    status, details = ss.ServiceStatus().proxmox_status(
        1,
        "https://proxbox.local:8800",
        auth_headers={"Authorization": "Bearer backend-token"},
        backend_verify_ssl=False,
    )

    assert status == "success"
    assert details["api_access"] == "success"
    assert proxmox_endpoint.mode == "standalone"
    assert endpoint_manager.filters == [{"pk": 1}]
    assert endpoint_manager.updates == [{"mode": "standalone"}]


def test_proxmox_mode_detects_standalone_via_backend_json(
    monkeypatch,
    fastapi_endpoint,
):
    proxmox_endpoint = SimpleNamespace(
        id=1,
        pk=1,
        name="pve01",
        domain="pve.local",
        ip_address="10.0.0.30/24",
        port=8006,
        verify_ssl=False,
        mode="undefined",
        save=lambda update_fields=None: pytest.fail("keepalive must not call save()"),
    )
    load_plugin_module(
        "netbox_proxbox.views.keepalive_status",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
        proxmox_endpoint=proxmox_endpoint,
    )
    ss = _service_status_module()
    endpoint_manager = _RecordingProxmoxEndpointManager(proxmox_endpoint)
    monkeypatch.setattr(ss.ProxmoxEndpoint, "objects", endpoint_manager)
    monkeypatch.setattr(ss.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(
        ss,
        "sync_proxmox_endpoint_to_backend",
        lambda *args, **kwargs: (True, None, None),
    )
    monkeypatch.setattr(
        ss,
        "resolve_backend_endpoint_id",
        lambda *args, **kwargs: (1, None),
    )
    monkeypatch.setattr(ss, "_last_proxmox_mode_check", {})
    monkeypatch.setattr(
        ss.requests,
        "get",
        lambda *args, **kwargs: ResponseStub([{"pve01": {"version": "8.3.0"}}]),
    )
    monkeypatch.setattr(
        _backend_proxy_module(),
        "request_backend_json",
        lambda *args, **kwargs: (
            {"ok": True, "response": [{"type": "node", "name": "pve01"}]},
            200,
        ),
    )

    status, details = ss.ServiceStatus().proxmox_status(
        1,
        "https://proxbox.local:8800",
        auth_headers={"Authorization": "Bearer backend-token"},
        backend_verify_ssl=False,
    )

    assert status == "success"
    assert details["api_access"] == "success"
    assert proxmox_endpoint.mode == "standalone"
    assert endpoint_manager.filters == [{"pk": 1}]
    assert endpoint_manager.updates == [{"mode": "standalone"}]


def test_proxmox_mode_detection_failure_leaves_status_and_mode_unchanged(
    monkeypatch,
    fastapi_endpoint,
):
    saved_calls = []
    proxmox_endpoint = SimpleNamespace(
        id=1,
        pk=1,
        name="pve01",
        domain="pve.local",
        ip_address="10.0.0.30/24",
        port=8006,
        verify_ssl=False,
        mode="undefined",
        save=lambda update_fields=None: saved_calls.append(update_fields),
    )
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
    monkeypatch.setattr(
        ss,
        "resolve_backend_endpoint_id",
        lambda *args, **kwargs: (1, None),
    )
    monkeypatch.setattr(ss, "_last_proxmox_mode_check", {})
    monkeypatch.setattr(
        ss.requests,
        "get",
        lambda *args, **kwargs: ResponseStub([{"pve01": {"version": "8.3.0"}}]),
    )
    monkeypatch.setattr(
        _backend_proxy_module(),
        "request_backend_json",
        lambda *args, **kwargs: (
            {"ok": False, "detail": "backend unavailable"},
            503,
        ),
    )

    status, details = ss.ServiceStatus().proxmox_status(
        1,
        "https://proxbox.local:8800",
        auth_headers={"Authorization": "Bearer backend-token"},
        backend_verify_ssl=False,
    )

    assert status == "success"
    assert details["api_access"] == "success"
    assert proxmox_endpoint.mode == "undefined"
    assert saved_calls == []


def test_proxmox_mode_detection_throttle_skips_fresh_detected_mode(
    monkeypatch,
    fastapi_endpoint,
):
    saved_calls = []
    proxmox_endpoint = SimpleNamespace(
        id=1,
        pk=1,
        name="pve01",
        domain="pve.local",
        ip_address="10.0.0.30/24",
        port=8006,
        verify_ssl=False,
        mode="cluster",
        save=lambda update_fields=None: saved_calls.append(update_fields),
    )
    load_plugin_module(
        "netbox_proxbox.views.keepalive_status",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
        proxmox_endpoint=proxmox_endpoint,
    )
    ss = _service_status_module()
    monkeypatch.setattr(ss.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(ss.time, "monotonic", lambda: 1000.0)
    monkeypatch.setattr(ss, "_last_proxmox_mode_check", {1: 1000.0})
    monkeypatch.setattr(
        ss,
        "sync_proxmox_endpoint_to_backend",
        lambda *args, **kwargs: (True, None, None),
    )
    monkeypatch.setattr(
        ss,
        "resolve_backend_endpoint_id",
        lambda *args, **kwargs: (1, None),
    )
    monkeypatch.setattr(
        ss.requests,
        "get",
        lambda *args, **kwargs: ResponseStub([{"pve01": {"version": "8.3.0"}}]),
    )
    monkeypatch.setattr(
        _backend_proxy_module(),
        "request_backend_json",
        lambda *args, **kwargs: pytest.fail("fresh mode throttle was ignored"),
    )

    status, details = ss.ServiceStatus().proxmox_status(
        1,
        "https://proxbox.local:8800",
        auth_headers={"Authorization": "Bearer backend-token"},
        backend_verify_ssl=False,
    )

    assert status == "success"
    assert details["api_access"] == "success"
    assert proxmox_endpoint.mode == "cluster"
    assert saved_calls == []
