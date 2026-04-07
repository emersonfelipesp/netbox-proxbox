"""Tests for test_backend_logs_view."""

from __future__ import annotations

from types import SimpleNamespace

from .conftest import load_plugin_module


def test_backend_logs_view_exposes_fastapi_and_logs_urls(monkeypatch):
    module = load_plugin_module(
        "netbox_proxbox.views.logs",
        monkeypatch=monkeypatch,
        fastapi_endpoint=SimpleNamespace(
            domain="proxbox.local",
            ip_address="10.0.0.5/24",
            port=8800,
            verify_ssl=True,
            websocket_port=8801,
            websocket_domain="proxbox.local",
            use_websocket=True,
        ),
        get_fastapi_url=lambda endpoint: {
            "http_url": "https://proxbox.local:8800",
            "websocket_url": "wss://proxbox.local:8801/ws",
        },
    )

    request = SimpleNamespace(
        method="GET",
        user=SimpleNamespace(is_authenticated=True),
    )
    response = module.BackendLogsView().get(request)
    context = response["context"]

    assert response["template"] == "netbox_proxbox/logs.html"
    assert context["fastapi_url"] == "https://proxbox.local:8800"
    assert context["fastapi_websocket_url"] == "wss://proxbox.local:8801/ws"
    assert context["logs_api_url"] == "https://proxbox.local:8800/admin/logs"
