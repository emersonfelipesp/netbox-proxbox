"""Tests for test_utils."""

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
        use_https=True,
        verify_ssl=True,
        websocket_port=8801,
        websocket_domain=None,
        use_websocket=False,
    )
    result = utils.get_fastapi_url(endpoint)

    assert result["http_url"] == "https://proxbox.backend.local:8800"


def test_get_fastapi_url_scheme_uses_use_https_not_verify_ssl(monkeypatch):
    """Issue #352: scheme must be driven by ``use_https`` only.

    With ``use_https=True`` and ``verify_ssl=False`` (the proxbox-api
    ``*-nginx`` image with the bundled mkcert cert) the URL must be
    ``https://...`` and the dict must report ``verify_ssl=False`` so the
    requests layer skips cert verification.
    """
    netbox_module = types.ModuleType("netbox")
    netbox_plugins = types.ModuleType("netbox.plugins")
    netbox_plugins.PluginConfig = type("PluginConfig", (), {})
    monkeypatch.setitem(sys.modules, "netbox", netbox_module)
    monkeypatch.setitem(sys.modules, "netbox.plugins", netbox_plugins)
    sys.modules.pop("netbox_proxbox.utils", None)

    utils = importlib.import_module("netbox_proxbox.utils")

    endpoint = SimpleNamespace(
        domain="proxbox.example.com",
        ip_address="10.0.0.5/24",
        port=8800,
        use_https=True,
        verify_ssl=False,
        websocket_port=None,
        websocket_domain=None,
        use_websocket=False,
    )
    result = utils.get_fastapi_url(endpoint)

    assert result["http_url"] == "https://proxbox.example.com:8800"
    assert result["websocket_url"] == "wss://10.0.0.5:8800/ws"
    assert result["ip_address_url"] == "https://10.0.0.5:8800"
    assert result["use_https"] is True
    assert result["verify_ssl"] is False


def test_get_fastapi_url_verify_ssl_alone_does_not_force_https(monkeypatch):
    """``verify_ssl`` without ``use_https`` keeps the URL on plain HTTP."""
    netbox_module = types.ModuleType("netbox")
    netbox_plugins = types.ModuleType("netbox.plugins")
    netbox_plugins.PluginConfig = type("PluginConfig", (), {})
    monkeypatch.setitem(sys.modules, "netbox", netbox_module)
    monkeypatch.setitem(sys.modules, "netbox.plugins", netbox_plugins)
    sys.modules.pop("netbox_proxbox.utils", None)

    utils = importlib.import_module("netbox_proxbox.utils")

    endpoint = SimpleNamespace(
        domain="proxbox.example.com",
        ip_address="10.0.0.5/24",
        port=8800,
        use_https=False,
        verify_ssl=True,
        websocket_port=None,
        websocket_domain=None,
        use_websocket=False,
    )
    result = utils.get_fastapi_url(endpoint)

    assert result["http_url"] == "http://proxbox.example.com:8800"
    assert result["websocket_url"] == "ws://10.0.0.5:8800/ws"
    assert result["use_https"] is False
    assert result["verify_ssl"] is True
