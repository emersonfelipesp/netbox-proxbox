"""Tests for test_openapi_schema_service."""

from __future__ import annotations

import importlib.util
import sys
from types import SimpleNamespace
from pathlib import Path


def _load_openapi_schema_module(monkeypatch):
    class _CacheRuntimeStub:
        def __init__(self):
            self.values = {}

        def get(self, key):
            return self.values.get(key)

        def set(self, key, value, timeout=None):
            self.values[key] = value

    django_cache_mod = SimpleNamespace(cache=_CacheRuntimeStub())
    django_core_cache = SimpleNamespace(cache=django_cache_mod.cache)
    models_stub = SimpleNamespace(FastAPIEndpoint=object)
    utils_stub = SimpleNamespace(
        get_backend_auth_headers=lambda endpoint: {},
        get_fastapi_url=lambda endpoint: {},
    )

    monkeypatch.setitem(sys.modules, "django", SimpleNamespace())
    monkeypatch.setitem(sys.modules, "django.core", SimpleNamespace())
    monkeypatch.setitem(sys.modules, "django.core.cache", django_core_cache)
    monkeypatch.setitem(sys.modules, "netbox_proxbox", SimpleNamespace())
    monkeypatch.setitem(sys.modules, "netbox_proxbox.models", models_stub)
    monkeypatch.setitem(sys.modules, "netbox_proxbox.utils", utils_stub)

    module_path = (
        Path(__file__).resolve().parents[1]
        / "netbox_proxbox"
        / "services"
        / "openapi_schema.py"
    )
    module_name = "test_openapi_schema_runtime"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _CacheStub:
    def __init__(self):
        self.values = {}

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value, timeout=None):
        self.values[key] = value


def test_openapi_schema_caches_by_backend_version(monkeypatch):
    openapi_schema = _load_openapi_schema_module(monkeypatch)
    cache = _CacheStub()
    monkeypatch.setattr(openapi_schema, "cache", cache)

    endpoint = SimpleNamespace(pk=7)
    monkeypatch.setattr(
        openapi_schema,
        "get_fastapi_url",
        lambda obj: {"http_url": "https://proxbox.local:8800", "verify_ssl": True},
    )
    monkeypatch.setattr(openapi_schema, "get_backend_auth_headers", lambda obj: {})

    calls = []

    def _fake_request(url, **kwargs):
        calls.append(url)
        if url.endswith("/version"):
            return {"version": "0.0.5"}, None
        if url.endswith("/openapi.json"):
            return {
                "info": {"title": "Proxbox API", "version": "0.0.5"},
                "paths": {
                    "/health": {
                        "get": {
                            "summary": "Health",
                            "responses": {"200": {"description": "ok"}},
                        }
                    }
                },
                "components": {"schemas": {"Health": {"type": "object"}}},
            }, None
        return None, "unexpected"

    monkeypatch.setattr(openapi_schema, "_request_json", _fake_request)

    first = openapi_schema.get_cached_openapi_schema(endpoint)
    second = openapi_schema.get_cached_openapi_schema(endpoint)

    assert first.get("cache_hit") is False
    assert second.get("cache_hit") is True
    assert first.get("refreshed_at")
    assert first["schema"]["stats"]["operations"] == 1
    assert first["backend_version"] == "0.0.5"
    assert calls.count("https://proxbox.local:8800/openapi.json") == 1


def test_openapi_schema_returns_error_when_openapi_fetch_fails(monkeypatch):
    openapi_schema = _load_openapi_schema_module(monkeypatch)
    cache = _CacheStub()
    monkeypatch.setattr(openapi_schema, "cache", cache)

    endpoint = SimpleNamespace(pk=8)
    monkeypatch.setattr(
        openapi_schema,
        "get_fastapi_url",
        lambda obj: {"http_url": "https://proxbox.local:8800", "verify_ssl": True},
    )
    monkeypatch.setattr(openapi_schema, "get_backend_auth_headers", lambda obj: {})

    def _fake_request(url, **kwargs):
        if url.endswith("/version"):
            return {"version": "0.0.6"}, None
        return None, "boom"

    monkeypatch.setattr(openapi_schema, "_request_json", _fake_request)

    result = openapi_schema.get_cached_openapi_schema(endpoint)
    assert "error" in result
    assert "openapi.json" in result["error"]


def test_openapi_schema_force_refresh_bypasses_cache(monkeypatch):
    openapi_schema = _load_openapi_schema_module(monkeypatch)
    cache = _CacheStub()
    monkeypatch.setattr(openapi_schema, "cache", cache)

    endpoint = SimpleNamespace(pk=9)
    monkeypatch.setattr(
        openapi_schema,
        "get_fastapi_url",
        lambda obj: {"http_url": "https://proxbox.local:8800", "verify_ssl": True},
    )
    monkeypatch.setattr(openapi_schema, "get_backend_auth_headers", lambda obj: {})

    calls = []

    def _fake_request(url, **kwargs):
        calls.append(url)
        if url.endswith("/version"):
            return {"version": "0.1.0"}, None
        if url.endswith("/openapi.json"):
            return {
                "info": {"title": "Proxbox API", "version": "0.1.0"},
                "paths": {
                    "/ping": {
                        "get": {
                            "summary": "Ping",
                            "responses": {"200": {"description": "ok"}},
                        }
                    }
                },
                "components": {"schemas": {}},
            }, None
        return None, "unexpected"

    monkeypatch.setattr(openapi_schema, "_request_json", _fake_request)

    first = openapi_schema.get_cached_openapi_schema(endpoint)
    forced = openapi_schema.get_cached_openapi_schema(endpoint, force_refresh=True)

    assert first["cache_hit"] is False
    assert forced["cache_hit"] is False
    assert forced["cache_forced"] is True
    assert forced.get("refreshed_at")
    assert calls.count("https://proxbox.local:8800/openapi.json") == 2
