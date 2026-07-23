"""Regression tests for endpoint enabled-state connection guards."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tests.django_stubs import install_django_stubs


REPO_ROOT = Path(__file__).resolve().parents[1]


def _source(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def _load_module(monkeypatch, module_name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(
        module_name, REPO_ROOT / relative_path
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, module_name, module)
    spec.loader.exec_module(module)
    return module


def _install_proxbox_package(monkeypatch):
    pkg = types.ModuleType("netbox_proxbox")
    pkg.__path__ = [str(REPO_ROOT / "netbox_proxbox")]
    monkeypatch.setitem(sys.modules, "netbox_proxbox", pkg)

    services_pkg = types.ModuleType("netbox_proxbox.services")
    services_pkg.__path__ = [str(REPO_ROOT / "netbox_proxbox" / "services")]
    monkeypatch.setitem(sys.modules, "netbox_proxbox.services", services_pkg)

    views_pkg = types.ModuleType("netbox_proxbox.views")
    views_pkg.__path__ = [str(REPO_ROOT / "netbox_proxbox" / "views")]
    monkeypatch.setitem(sys.modules, "netbox_proxbox.views", views_pkg)

    return _load_module(
        monkeypatch,
        "netbox_proxbox.services.endpoint_enabled",
        "netbox_proxbox/services/endpoint_enabled.py",
    )


def _load_backend_sync_module(monkeypatch):
    # `DatabaseError` / `salted_hmac` are imported at module level — see
    # `tests/django_stubs.py` for why every loader of this file needs them.
    install_django_stubs(monkeypatch)

    _install_proxbox_package(monkeypatch)

    models_mod = types.ModuleType("netbox_proxbox.models")
    models_mod.ProxmoxEndpoint = object
    monkeypatch.setitem(sys.modules, "netbox_proxbox.models", models_mod)

    utils_mod = types.ModuleType("netbox_proxbox.utils")
    utils_mod.get_ip_address_host = lambda value: (
        str(value).split("/")[0] if value else "127.0.0.1"
    )
    monkeypatch.setitem(sys.modules, "netbox_proxbox.utils", utils_mod)

    error_utils_mod = types.ModuleType("netbox_proxbox.views.error_utils")
    error_utils_mod.extract_backend_error_detail = lambda exc: (str(exc), None)
    error_utils_mod.parse_requests_response_json = lambda response, log_label=None: (
        {},
        None,
    )
    monkeypatch.setitem(
        sys.modules, "netbox_proxbox.views.error_utils", error_utils_mod
    )

    return _load_module(
        monkeypatch,
        "netbox_proxbox.views.backend_sync",
        "netbox_proxbox/views/backend_sync.py",
    )


def _load_openapi_schema_module(monkeypatch):
    _install_proxbox_package(monkeypatch)

    django_module = types.ModuleType("django")
    django_core = types.ModuleType("django.core")
    django_cache = types.ModuleType("django.core.cache")
    django_cache.cache = SimpleNamespace(get=lambda key: None, set=lambda *a, **k: None)
    django_core.cache = django_cache
    django_module.core = django_core
    monkeypatch.setitem(sys.modules, "django", django_module)
    monkeypatch.setitem(sys.modules, "django.core", django_core)
    monkeypatch.setitem(sys.modules, "django.core.cache", django_cache)

    models_mod = types.ModuleType("netbox_proxbox.models")
    models_mod.FastAPIEndpoint = object
    monkeypatch.setitem(sys.modules, "netbox_proxbox.models", models_mod)

    schema_mod = types.ModuleType("netbox_proxbox.schemas.openapi_schema")
    schema_mod.OpenAPISummary = SimpleNamespace(from_raw_payload=lambda payload: None)
    monkeypatch.setitem(
        sys.modules, "netbox_proxbox.schemas.openapi_schema", schema_mod
    )

    errors_mod = types.ModuleType("netbox_proxbox.services._endpoint_errors")
    errors_mod.translate_request_exception = lambda exc: str(exc)
    monkeypatch.setitem(
        sys.modules, "netbox_proxbox.services._endpoint_errors", errors_mod
    )

    utils_mod = types.ModuleType("netbox_proxbox.utils")
    utils_mod.get_backend_auth_headers = lambda endpoint: {}
    utils_mod.get_fastapi_url = lambda endpoint: {"http_url": "https://proxbox.local"}
    monkeypatch.setitem(sys.modules, "netbox_proxbox.utils", utils_mod)

    return _load_module(
        monkeypatch,
        "netbox_proxbox.services.openapi_schema",
        "netbox_proxbox/services/openapi_schema.py",
    )


def test_pbs_and_pdm_models_reuse_endpoint_base_enabled_field():
    base_source = _source("netbox_proxbox/models/base.py")
    pbs_source = _source("netbox_proxbox/models/pbs_endpoint.py")
    pdm_source = _source("netbox_proxbox/models/pdm_endpoint.py")

    assert "class EndpointBase(CommonProperties, NetBoxModel):" in base_source
    assert "enabled = models.BooleanField" in base_source
    assert "class PBSEndpoint(EndpointBase):" in pbs_source
    assert "class PDMEndpoint(EndpointBase):" in pdm_source
    assert "enabled = models.BooleanField" not in pbs_source
    assert "enabled = models.BooleanField" not in pdm_source


def test_endpoint_enabled_guard_wired_into_connection_paths():
    guarded_paths = (
        "netbox_proxbox/__init__.py",
        "netbox_proxbox/signals.py",
        "netbox_proxbox/models/fastapi_endpoint.py",
        "netbox_proxbox/services/backend_auth.py",
        "netbox_proxbox/services/backend_context.py",
        "netbox_proxbox/services/openapi_schema.py",
        "netbox_proxbox/services/service_status.py",
        "netbox_proxbox/views/backend_sync.py",
        "netbox_proxbox/views/keepalive_status.py",
        "netbox_proxbox/management/commands/proxbox_fix_tokens.py",
    )

    for relative_path in guarded_paths:
        module_source = _source(relative_path)
        assert "enabled" in module_source, relative_path

    shared_guard_paths = (
        "netbox_proxbox/services/openapi_schema.py",
        "netbox_proxbox/services/service_status.py",
        "netbox_proxbox/views/backend_sync.py",
        "netbox_proxbox/views/keepalive_status.py",
    )

    for relative_path in shared_guard_paths:
        module_source = _source(relative_path)
        assert "disabled_endpoint_detail" in module_source, relative_path


def test_disabled_endpoint_detail_supports_pdm_endpoint_objects(monkeypatch):
    endpoint_enabled = _install_proxbox_package(monkeypatch)
    endpoint = SimpleNamespace(
        pk=9,
        name="pdm-east",
        host="10.0.30.150",
        port=8443,
        enabled=False,
    )

    assert endpoint_enabled.endpoint_is_enabled(endpoint) is False
    assert (
        endpoint_enabled.disabled_endpoint_detail(
            endpoint, kind="PDM endpoint", action="skipping status check"
        )
        == "PDM endpoint 'pdm-east' (id=9) is disabled; skipping status check."
    )


def test_enabled_endpoint_detail_returns_none(monkeypatch):
    endpoint_enabled = _install_proxbox_package(monkeypatch)
    endpoint = SimpleNamespace(pk=9, name="pdm-east", enabled=True)

    assert endpoint_enabled.endpoint_is_enabled(endpoint) is True
    assert (
        endpoint_enabled.disabled_endpoint_detail(endpoint, kind="PDM endpoint") is None
    )


def test_disabled_netbox_endpoint_backend_sync_does_not_connect(monkeypatch):
    backend_sync = _load_backend_sync_module(monkeypatch)
    endpoint = SimpleNamespace(
        pk=1,
        name="netbox",
        ip_address=SimpleNamespace(address="10.0.30.20/24"),
        domain="",
        port=443,
        verify_ssl=True,
        effective_token_version="v1",
        effective_token_value="token",
        token_key="",
        token_secret="",
        enabled=False,
    )

    with patch("netbox_proxbox.views.backend_sync.requests.get") as mock_get:
        ok, detail, http_status = backend_sync.sync_netbox_endpoint_to_backend(
            endpoint,
            base_url="https://proxbox.local:8800",
            auth_headers={"Authorization": "Bearer backend-token"},
        )

    assert ok is False
    assert http_status is None
    assert "disabled" in (detail or "")
    mock_get.assert_not_called()


def test_disabled_fastapi_openapi_schema_does_not_connect(monkeypatch):
    openapi_schema = _load_openapi_schema_module(monkeypatch)
    endpoint = SimpleNamespace(
        pk=1,
        name="proxbox-api",
        domain="proxbox.local",
        ip_address="10.0.30.10/24",
        port=8800,
        verify_ssl=True,
        use_https=True,
        token="token",
        enabled=False,
    )

    with patch("netbox_proxbox.services.openapi_schema.requests.get") as mock_get:
        payload = openapi_schema.get_cached_openapi_schema(endpoint)

    assert "disabled" in payload["error"]
    mock_get.assert_not_called()
