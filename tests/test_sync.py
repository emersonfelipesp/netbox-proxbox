from __future__ import annotations

from types import SimpleNamespace

import requests

from tests.conftest import ResponseStub, load_plugin_module


def _json_request(method: str = "POST"):
    return SimpleNamespace(
        method=method,
        headers={
            "Accept": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        },
    )


def _browser_request(method: str = "POST"):
    return SimpleNamespace(method=method, headers={"Accept": "text/html"})


def test_sync_resource_uses_primary_fastapi_url(monkeypatch, fastapi_endpoint):
    module = load_plugin_module(
        "netbox_proxbox.views.sync",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
    )
    requested = []

    monkeypatch.setattr(
        module.requests,
        "get",
        lambda url, params=None, headers=None, verify=True, timeout=None: (
            requested.append((url, params, headers, verify))
            or ResponseStub({"ok": True})
        ),
    )

    response = module.sync_devices(_json_request())
    assert response.status_code == 202
    assert response.payload["queued"] is True
    assert requested == [
        (
            "https://proxbox.local:8800/dcim/devices/create",
            None,
            {"Authorization": "Bearer backend-token"},
            True,
        )
    ]


def test_sync_resource_falls_back_to_ip_url(monkeypatch, fastapi_endpoint):
    module = load_plugin_module(
        "netbox_proxbox.views.sync",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
    )
    requested = []

    def fake_get(url, params=None, headers=None, verify=True, timeout=None):
        requested.append((url, params, headers, verify))
        if "proxbox.local" in url:
            raise requests.exceptions.ConnectionError("primary failed")
        return ResponseStub({"ok": True})

    monkeypatch.setattr(module.requests, "get", fake_get)

    response = module.sync_vm_backups(_json_request())
    assert response.status_code == 202
    assert response.payload["queued"] is True
    assert requested == [
        (
            "https://proxbox.local:8800/virtualization/virtual-machines/backups/all/create",
            {"delete_nonexistent_backup": True},
            {"Authorization": "Bearer backend-token"},
            True,
        ),
        (
            "https://10.0.0.5:8800/virtualization/virtual-machines/backups/all/create",
            {"delete_nonexistent_backup": True},
            {"Authorization": "Bearer backend-token"},
            True,
        ),
    ]


def test_sync_resource_uses_http_ip_fallback_when_ssl_verification_is_disabled(
    monkeypatch, fastapi_endpoint
):
    endpoint = SimpleNamespace(**(fastapi_endpoint.__dict__ | {"verify_ssl": False}))
    module = load_plugin_module(
        "netbox_proxbox.views.sync",
        monkeypatch=monkeypatch,
        fastapi_endpoint=endpoint,
        get_fastapi_url=lambda obj: {
            "http_url": "http://proxbox.local:8800",
            "ip_address_url": "http://10.0.0.5:8800",
            "verify_ssl": False,
            "websocket_url": "ws://proxbox.local:8801/ws",
        },
    )
    requested = []

    def fake_get(url, params=None, headers=None, verify=True, timeout=None):
        requested.append((url, headers, verify))
        if "proxbox.local" in url:
            raise requests.exceptions.ConnectionError(
                "dial tcp 10.0.0.5:8800: connect: refused"
            )
        return ResponseStub({"ok": True})

    monkeypatch.setattr(module.requests, "get", fake_get)

    response = module.sync_full_update(_json_request())

    assert response.status_code == 202
    assert requested == [
        (
            "http://proxbox.local:8800/dcim/devices/create",
            {"Authorization": "Bearer backend-token"},
            False,
        ),
        (
            "http://10.0.0.5:8800/dcim/devices/create",
            {"Authorization": "Bearer backend-token"},
            False,
        ),
        (
            "http://proxbox.local:8800/virtualization/virtual-machines/create",
            {"Authorization": "Bearer backend-token"},
            False,
        ),
        (
            "http://10.0.0.5:8800/virtualization/virtual-machines/create",
            {"Authorization": "Bearer backend-token"},
            False,
        ),
    ]


def test_sync_resource_skips_duplicate_ip_fallback(monkeypatch, fastapi_endpoint):
    endpoint = SimpleNamespace(**(fastapi_endpoint.__dict__ | {"domain": ""}))
    module = load_plugin_module(
        "netbox_proxbox.views.sync",
        monkeypatch=monkeypatch,
        fastapi_endpoint=endpoint,
        get_fastapi_url=lambda obj: {
            "http_url": "https://10.0.0.5:8800",
            "ip_address_url": "https://10.0.0.5:8800",
            "verify_ssl": True,
            "websocket_url": "wss://10.0.0.5:8801/ws",
        },
    )
    requested = []

    monkeypatch.setattr(
        module.requests,
        "get",
        lambda url, params=None, headers=None, verify=True, timeout=None: (
            requested.append((url, headers, verify)) or ResponseStub({"ok": True})
        ),
    )

    response = module.sync_devices(_json_request())

    assert response.status_code == 202
    assert requested == [
        (
            "https://10.0.0.5:8800/dcim/devices/create",
            {"Authorization": "Bearer backend-token"},
            True,
        )
    ]


def test_sync_resource_redirects_browser_requests_with_success_message(
    monkeypatch, fastapi_endpoint
):
    module = load_plugin_module(
        "netbox_proxbox.views.sync",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
    )

    monkeypatch.setattr(
        module.requests, "get", lambda *args, **kwargs: ResponseStub({"ok": True})
    )

    response = module.sync_virtual_machines(_browser_request())

    assert response == {"redirect": "plugins:netbox_proxbox:home"}
    assert module._messages_stub.calls == [
        ("success", "Virtual machines sync queued successfully.")
    ]


def test_sync_resource_redirects_browser_requests_with_error_message(
    monkeypatch, fastapi_endpoint
):
    module = load_plugin_module(
        "netbox_proxbox.views.sync",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
    )

    monkeypatch.setattr(
        module.requests,
        "get",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            requests.exceptions.ConnectionError("connection refused")
        ),
    )

    response = module.sync_full_update(_browser_request())

    assert response == {"redirect": "plugins:netbox_proxbox:home"}
    assert module._messages_stub.calls == [("error", "connection refused")]


def test_sync_full_update_runs_devices_then_virtual_machines(
    monkeypatch, fastapi_endpoint
):
    module = load_plugin_module(
        "netbox_proxbox.views.sync",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
    )
    requested = []

    def fake_get(url, params=None, headers=None, verify=True, timeout=None):
        requested.append((url, headers, verify))
        return ResponseStub({"ok": True, "url": url})

    monkeypatch.setattr(module.requests, "get", fake_get)

    response = module.sync_full_update(_json_request())

    assert response.status_code == 202
    assert requested == [
        (
            "https://proxbox.local:8800/dcim/devices/create",
            {"Authorization": "Bearer backend-token"},
            True,
        ),
        (
            "https://proxbox.local:8800/virtualization/virtual-machines/create",
            {"Authorization": "Bearer backend-token"},
            True,
        ),
    ]
    assert response.payload["path"] == "full-update"
    assert response.payload["detail"] == "Full update sync completed successfully."
    assert response.payload["response"]["devices"]["ok"] is True
    assert response.payload["response"]["virtual-machines"]["ok"] is True


def test_sync_full_update_stops_when_devices_step_fails(monkeypatch, fastapi_endpoint):
    module = load_plugin_module(
        "netbox_proxbox.views.sync",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
    )

    class FailingResponse(ResponseStub):
        text = '{"detail": "devices failed"}'
        headers = {"Content-Type": "application/json"}
        url = "https://proxbox.local:8800/dcim/devices/create"

        def raise_for_status(self):
            err = requests.exceptions.HTTPError("500")
            err.response = self
            raise err

    requested = []

    def fake_get(url, params=None, headers=None, verify=True, timeout=None):
        requested.append(url)
        if url.endswith("/dcim/devices/create"):
            return FailingResponse({"detail": "devices failed"}, status_code=500)
        return ResponseStub({"ok": True})

    monkeypatch.setattr(module.requests, "get", fake_get)

    response = module.sync_full_update(_json_request())

    assert response.status_code == 503
    assert requested == ["https://proxbox.local:8800/dcim/devices/create"]
    assert response.payload["stage"] == "devices"
    assert response.payload["detail"] == "devices failed"


def test_sync_resource_surfaces_backend_error_detail(monkeypatch, fastapi_endpoint):
    module = load_plugin_module(
        "netbox_proxbox.views.sync",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
    )

    class FailingResponse(ResponseStub):
        text = '{"detail": "backend token missing"}'
        headers = {"Content-Type": "application/json"}
        url = "https://proxbox.local:8800/full-update"

        def raise_for_status(self):
            err = requests.exceptions.HTTPError("401")
            err.response = self
            raise err

    monkeypatch.setattr(
        module.requests,
        "get",
        lambda *args, **kwargs: FailingResponse(
            {"detail": "backend token missing"},
            status_code=401,
        ),
    )

    response = module.sync_devices(_json_request())

    assert response.status_code == 503
    assert response.payload["detail"] == "backend token missing"


def test_sync_resource_prefers_backend_message_over_generic_internal_server_error(
    monkeypatch, fastapi_endpoint
):
    module = load_plugin_module(
        "netbox_proxbox.views.sync",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
    )

    class FailingResponse(ResponseStub):
        text = '{"detail": "Internal Server Error", "message": "Error while syncing virtual machines."}'
        headers = {"Content-Type": "application/json"}
        url = "https://proxbox.local:8800/full-update"

        def raise_for_status(self):
            err = requests.exceptions.HTTPError("500")
            err.response = self
            raise err

    monkeypatch.setattr(
        module.requests,
        "get",
        lambda *args, **kwargs: FailingResponse(
            {
                "detail": "Internal Server Error",
                "message": "Error while syncing virtual machines.",
            },
            status_code=500,
        ),
    )

    response = module.sync_devices(_json_request())

    assert response.status_code == 503
    assert response.payload["detail"] == "Error while syncing virtual machines."


def test_sync_full_update_surfaces_structured_backend_type_error(
    monkeypatch, fastapi_endpoint
):
    module = load_plugin_module(
        "netbox_proxbox.views.sync",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
    )

    class FailingResponse(ResponseStub):
        text = (
            '{"detail": "\'async for\' requires an object with __aiter__ method, got PluginsApp", '
            '"message": "Error ensuring Proxbox tag"}'
        )
        headers = {"Content-Type": "application/json"}
        url = "https://proxbox.local:8800/dcim/devices/create"

        def raise_for_status(self):
            err = requests.exceptions.HTTPError("500")
            err.response = self
            raise err

    monkeypatch.setattr(
        module.requests,
        "get",
        lambda *args, **kwargs: FailingResponse(
            {
                "detail": "'async for' requires an object with __aiter__ method, got PluginsApp",
                "message": "Error ensuring Proxbox tag",
            },
            status_code=500,
        ),
    )

    response = module.sync_full_update(_json_request())

    assert response.status_code == 503
    assert response.payload["stage"] == "devices"
    assert response.payload["detail"] == (
        "'async for' requires an object with __aiter__ method, got PluginsApp"
    )


def test_sync_stream_response_returns_sse(monkeypatch, fastapi_endpoint):
    module = load_plugin_module(
        "netbox_proxbox.views.sync",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
    )

    class _Response:
        status_code = 200

        def raise_for_status(self):
            return None

        def iter_lines(self, decode_unicode=True):
            del decode_unicode
            return iter(
                [
                    "event: step",
                    'data: {"step":"devices","status":"started","message":"Starting."}',
                    "",
                    "event: complete",
                    'data: {"ok":true,"message":"Done."}',
                    "",
                ]
            )

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            del exc_type, exc, tb
            return False

    monkeypatch.setattr(module.requests, "get", lambda *args, **kwargs: _Response())

    response = module.sync_devices_stream(_json_request(method="GET"))
    chunks = list(response.streaming_content)

    assert response.status_code == 200
    assert response["Cache-Control"] == "no-cache"
    assert any("event: step" in chunk for chunk in chunks)
    assert any("event: complete" in chunk for chunk in chunks)
