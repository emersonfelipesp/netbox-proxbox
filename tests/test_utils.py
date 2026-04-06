from __future__ import annotations

import importlib
import subprocess
import sys
import types
from types import SimpleNamespace


def test_get_fastapi_url_builds_http_and_websocket_urls(monkeypatch):
    netbox_module = types.ModuleType("netbox")
    netbox_plugins = types.ModuleType("netbox.plugins")
    netbox_plugins.PluginConfig = type("PluginConfig", (), {})
    monkeypatch.setitem(sys.modules, "netbox", netbox_module)
    monkeypatch.setitem(sys.modules, "netbox.plugins", netbox_plugins)
    sys.modules.pop("netbox_proxbox.utils", None)

    utils = importlib.import_module("netbox_proxbox.utils")

    endpoint = SimpleNamespace(
        domain="proxbox.local",
        ip_address="10.0.0.5/24",
        port=8800,
        verify_ssl=False,
        websocket_port=8801,
        websocket_domain="ws.proxbox.local",
        use_websocket=True,
    )
    result = utils.get_fastapi_url(endpoint)

    assert result["http_url"] == "http://proxbox.local:8800"
    assert result["websocket_url"] == "ws://ws.proxbox.local:8801/ws"
    assert result["ip_address_url"] == "http://10.0.0.5:8800"


def test_get_backend_auth_headers_uses_api_key_header(monkeypatch):
    netbox_module = types.ModuleType("netbox")
    netbox_plugins = types.ModuleType("netbox.plugins")
    netbox_plugins.PluginConfig = type("PluginConfig", (), {})
    monkeypatch.setitem(sys.modules, "netbox", netbox_module)
    monkeypatch.setitem(sys.modules, "netbox.plugins", netbox_plugins)
    sys.modules.pop("netbox_proxbox.utils", None)

    utils = importlib.import_module("netbox_proxbox.utils")

    assert utils.get_backend_auth_headers(SimpleNamespace(token="")) == {}
    assert utils.get_backend_auth_headers(SimpleNamespace(token="abc")) == {
        "X-Proxbox-API-Key": "abc"
    }
    assert utils.get_backend_auth_headers(SimpleNamespace(token="  abc  ")) == {
        "X-Proxbox-API-Key": "abc"
    }


def test_get_fastapi_url_configures_mkcert_bundle_for_local_https(monkeypatch):
    netbox_module = types.ModuleType("netbox")
    netbox_plugins = types.ModuleType("netbox.plugins")
    netbox_plugins.PluginConfig = type("PluginConfig", (), {})
    monkeypatch.setitem(sys.modules, "netbox", netbox_module)
    monkeypatch.setitem(sys.modules, "netbox.plugins", netbox_plugins)
    sys.modules.pop("netbox_proxbox.utils", None)

    utils = importlib.import_module("netbox_proxbox.utils")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(stdout="/tmp/mkcert-root\n"),
    )

    endpoint = SimpleNamespace(
        domain="proxbox.backend.local",
        ip_address="127.0.0.1/32",
        port=8800,
        verify_ssl=True,
        websocket_port=8801,
        websocket_domain=None,
        use_websocket=False,
    )
    result = utils.get_fastapi_url(endpoint)

    assert result["http_url"] == "https://proxbox.backend.local:8800"
