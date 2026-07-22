"""Tests for Proxmox endpoint placement metadata sent to proxbox-api."""

from __future__ import annotations

import importlib.util
import sys
import types
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from tests.django_stubs import install_django_stubs


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_backend_sync_module(monkeypatch):
    # `DatabaseError` / `salted_hmac` are imported at module level — see
    # `tests/django_stubs.py` for why every loader of this file needs them.
    install_django_stubs(monkeypatch)

    pkg = types.ModuleType("netbox_proxbox")
    pkg.__path__ = [str(REPO_ROOT / "netbox_proxbox")]
    monkeypatch.setitem(sys.modules, "netbox_proxbox", pkg)

    views_pkg = types.ModuleType("netbox_proxbox.views")
    views_pkg.__path__ = [str(REPO_ROOT / "netbox_proxbox" / "views")]
    monkeypatch.setitem(sys.modules, "netbox_proxbox.views", views_pkg)

    services_pkg = types.ModuleType("netbox_proxbox.services")
    services_pkg.__path__ = [str(REPO_ROOT / "netbox_proxbox" / "services")]
    monkeypatch.setitem(sys.modules, "netbox_proxbox.services", services_pkg)

    endpoint_enabled_mod = types.ModuleType("netbox_proxbox.services.endpoint_enabled")
    endpoint_enabled_mod.disabled_endpoint_detail = lambda endpoint, **kwargs: None
    monkeypatch.setitem(
        sys.modules,
        "netbox_proxbox.services.endpoint_enabled",
        endpoint_enabled_mod,
    )

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

    spec = importlib.util.spec_from_file_location(
        "netbox_proxbox.views.backend_sync",
        REPO_ROOT / "netbox_proxbox" / "views" / "backend_sync.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "netbox_proxbox.views.backend_sync", module)
    spec.loader.exec_module(module)
    return module


def test_proxmox_backend_payload_includes_site_and_tenant_metadata(monkeypatch) -> None:
    backend_sync = _load_backend_sync_module(monkeypatch)
    endpoint = SimpleNamespace(
        pk=123,
        name="PVE",
        ip_address="10.0.0.10/32",
        domain="pve.example.com",
        port=8006,
        username="root@pam",
        password="secret",
        verify_ssl=False,
        timeout=30,
        max_retries=3,
        retry_backoff=Decimal("1.25"),
        token_name=None,
        token_value=None,
        site=SimpleNamespace(pk=42, slug="dc1", name="DC 1"),
        tenant=SimpleNamespace(pk=9, slug="customer-a", name="Customer A"),
    )

    payload = backend_sync._proxmox_backend_payload(endpoint)

    assert payload["verify_ssl"] is False
    assert payload["timeout"] == 30
    assert payload["max_retries"] == 3
    assert payload["retry_backoff"] == 1.25
    assert payload["site_id"] == 42
    assert payload["site_slug"] == "dc1"
    assert payload["site_name"] == "DC 1"
    assert payload["tenant_id"] == 9
    assert payload["tenant_slug"] == "customer-a"
    assert payload["tenant_name"] == "Customer A"


def _payload_for_access_methods(monkeypatch, value):
    backend_sync = _load_backend_sync_module(monkeypatch)
    endpoint = SimpleNamespace(
        pk=1,
        name="PVE",
        ip_address="10.0.0.10/32",
        domain="pve.example.com",
        port=8006,
        username="root@pam",
        password="secret",
        verify_ssl=False,
        timeout=None,
        max_retries=None,
        retry_backoff=None,
        token_name=None,
        token_value=None,
        access_methods=value,
        site=None,
        tenant=None,
    )
    return backend_sync._proxmox_backend_payload(endpoint)


def test_proxmox_backend_payload_pushes_access_methods(monkeypatch) -> None:
    assert (
        _payload_for_access_methods(monkeypatch, "api_ssh")["access_methods"]
        == "api_ssh"
    )
    assert _payload_for_access_methods(monkeypatch, "api")["access_methods"] == "api"


def test_proxmox_backend_payload_defaults_access_methods_to_api(monkeypatch) -> None:
    # Missing/blank access_methods falls back to "api" (API-only) in the payload.
    assert _payload_for_access_methods(monkeypatch, "")["access_methods"] == "api"
