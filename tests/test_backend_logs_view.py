"""Tests for test_backend_logs_view."""

from __future__ import annotations

from types import SimpleNamespace

from .conftest import load_plugin_module


def test_backend_logs_view_exposes_fastapi_and_logs_urls(monkeypatch):
    proxbox_settings = SimpleNamespace(
        backend_log_file_path="/custom/proxbox.log",
        save=lambda **kwargs: None,
    )
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
        proxbox_settings=proxbox_settings,
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
    assert context["backend_log_file_path"] == "/custom/proxbox.log"
    assert context["save_log_path_api_url"] == "/dummy/"


def test_backend_log_path_update_view_persists_valid_absolute_path(monkeypatch):
    saved = {"update_fields": None}

    def _save(**kwargs):
        saved["update_fields"] = kwargs.get("update_fields")

    proxbox_settings = SimpleNamespace(
        backend_log_file_path="/var/log/proxbox.log",
        save=_save,
    )
    module = load_plugin_module(
        "netbox_proxbox.views.logs",
        monkeypatch=monkeypatch,
        proxbox_settings=proxbox_settings,
    )

    request = SimpleNamespace(
        method="POST",
        POST={"backend_log_file_path": "/tmp/proxbox-custom.log"},
        user=SimpleNamespace(is_authenticated=True),
    )
    response = module.BackendLogPathUpdateView().post(request)

    assert response.status_code == 200
    assert response.payload["ok"] is True
    assert response.payload["backend_log_file_path"] == "/tmp/proxbox-custom.log"
    assert proxbox_settings.backend_log_file_path == "/tmp/proxbox-custom.log"
    assert saved["update_fields"] == ["backend_log_file_path"]


def test_backend_log_path_update_view_rejects_relative_path(monkeypatch):
    proxbox_settings = SimpleNamespace(
        backend_log_file_path="/var/log/proxbox.log",
        save=lambda **kwargs: None,
    )
    module = load_plugin_module(
        "netbox_proxbox.views.logs",
        monkeypatch=monkeypatch,
        proxbox_settings=proxbox_settings,
    )

    request = SimpleNamespace(
        method="POST",
        POST={"backend_log_file_path": "var/log/proxbox.log"},
        user=SimpleNamespace(is_authenticated=True),
    )
    response = module.BackendLogPathUpdateView().post(request)

    assert response.status_code == 400
    assert response.payload["ok"] is False
    assert "must be absolute" in response.payload["error"]
