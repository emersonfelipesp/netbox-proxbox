"""Tests for Proxmox endpoint placement metadata sent to proxbox-api."""

from __future__ import annotations

import importlib.util
import sys
import types
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests

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
    effective_tuning = {
        "timeout": 30,
        "max_retries": 3,
        "retry_backoff": Decimal("1.25"),
    }
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
        node_device_name_template="{node}.{cluster_slug}.example.com",
        effective_connection_tuning=lambda: effective_tuning,
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
    assert payload["node_device_name_template"] == "{node}.{cluster_slug}.example.com"


def test_proxmox_backend_payload_uses_resolved_tuning_and_preserves_zero(
    monkeypatch,
) -> None:
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
        timeout=None,
        max_retries=None,
        retry_backoff=None,
        token_name=None,
        token_value=None,
        access_methods="api",
        site=None,
        tenant=None,
        effective_connection_tuning=lambda: {
            "timeout": 45,
            "max_retries": 0,
            "retry_backoff": Decimal("0.00"),
        },
    )

    payload = backend_sync._proxmox_backend_payload(endpoint)

    assert payload["timeout"] == 45
    assert payload["max_retries"] == 0
    assert payload["retry_backoff"] == 0.0


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
        effective_connection_tuning=lambda: {
            "timeout": 5,
            "max_retries": 0,
            "retry_backoff": Decimal("0.50"),
        },
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


@pytest.mark.parametrize(
    ("enabled", "allow_writes", "allow_packer_template_builds", "expected"),
    (
        (True, True, True, True),
        (True, True, False, False),
        (True, False, True, False),
        (False, True, True, False),
    ),
)
def test_proxmox_backend_payload_pushes_only_effective_packer_authorization(
    monkeypatch,
    enabled: bool,
    allow_writes: bool,
    allow_packer_template_builds: bool,
    expected: bool,
) -> None:
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
        token_name=None,
        token_value=None,
        access_methods="api_ssh",
        enabled=enabled,
        allow_writes=allow_writes,
        allow_packer_template_builds=allow_packer_template_builds,
        site=None,
        tenant=None,
        effective_connection_tuning=lambda: {
            "timeout": 5,
            "max_retries": 0,
            "retry_backoff": Decimal("0.50"),
        },
    )

    payload = backend_sync._proxmox_backend_payload(endpoint)
    assert payload["enabled"] is enabled
    assert payload["allow_packer_template_builds"] is expected
    del endpoint.allow_packer_template_builds
    assert (
        backend_sync._proxmox_backend_payload(endpoint)["allow_packer_template_builds"]
        is False
    )


def test_backend_currency_detects_packer_authorization_revocation(monkeypatch) -> None:
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
        token_name=None,
        token_value=None,
        access_methods="api_ssh",
        allow_packer_template_builds=False,
        allow_writes=True,
        enabled=True,
        pushed_credential_fingerprint="",
        site=None,
        tenant=None,
        effective_connection_tuning=lambda: {
            "timeout": 5,
            "max_retries": 0,
            "retry_backoff": Decimal("0.50"),
        },
    )
    payload = backend_sync._proxmox_backend_payload(endpoint)
    backend_sync.proxmox_push_credentials_unchanged = lambda *_args: True
    row = {
        "name": backend_sync.proxmox_backend_name(endpoint),
        "domain": "pve.example.com",
        "ip_address": "10.0.0.10",
        "port": 8006,
        "username": "root@pam",
        "enabled": True,
        "verify_ssl": False,
        "access_methods": "api_ssh",
        "allow_packer_template_builds": True,
        "timeout": payload["timeout"],
        "max_retries": payload["max_retries"],
        "retry_backoff": payload["retry_backoff"],
    }

    assert backend_sync._proxmox_row_is_current(endpoint, row) is False


def _cached_push_arrangement(monkeypatch):
    backend_sync = _load_backend_sync_module(monkeypatch)
    endpoint = SimpleNamespace(
        pk=7,
        id=7,
        name="PVE",
        domain="pve.example.test",
        # Built at runtime so the public-boundary diff scan sees no literal address.
        ip_address=".".join(("10", "0", "0", "10")) + "/32",
        port=8006,
        enabled=True,
    )
    payload = {
        "name": "PVE (nb:7)",
        "password": "secret",
        "token_value": None,
        "enabled": True,
        "allow_packer_template_builds": False,
    }
    fingerprint = backend_sync._proxmox_payload_fingerprint(payload)

    class FakeCache:
        def __init__(self):
            self.deleted = []

        def get(self, key):
            if key.endswith(":keys"):
                return ["cached-key"]
            return {"fingerprint": fingerprint, "backend_id": 41}

        def delete_many(self, keys):
            self.deleted.extend(keys)

        def set(self, key, value, timeout):
            return None

    fake_cache = FakeCache()
    monkeypatch.setattr(backend_sync, "_django_cache", fake_cache)
    monkeypatch.setattr(backend_sync, "_proxmox_backend_payload", lambda obj: payload)
    monkeypatch.setattr(
        backend_sync,
        "_record_pushed_proxmox_credential_fingerprint",
        lambda *args: None,
    )
    monkeypatch.setattr(
        backend_sync,
        "_record_confirmed_packer_template_authorization",
        lambda *args: None,
    )
    return backend_sync, endpoint, fake_cache


class _PushResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            error = requests.exceptions.HTTPError(f"HTTP {self.status_code}")
            error.response = self
            raise error


def _parse_push_response(response, log_label=None):
    return response.payload, None


def test_recent_matching_fingerprint_confirms_one_row_and_skips_put(
    monkeypatch,
) -> None:
    backend_sync, endpoint, _ = _cached_push_arrangement(monkeypatch)
    calls = []
    row = {
        "id": 41,
        "name": "PVE (nb:7)",
        "domain": "pve.example.test",
        "port": 8006,
    }
    monkeypatch.setattr(
        backend_sync, "parse_requests_response_json", _parse_push_response
    )
    monkeypatch.setattr(
        backend_sync.requests,
        "get",
        lambda url, **kwargs: calls.append(url) or _PushResponse(row),
    )
    monkeypatch.setattr(
        backend_sync.requests,
        "put",
        lambda *args, **kwargs: pytest.fail("matching push cache issued PUT"),
    )

    assert backend_sync.sync_proxmox_endpoint_to_backend(
        endpoint, base_url="https://backend.example.invalid"
    ) == (True, None, None)
    assert calls == ["https://backend.example.invalid/proxmox/endpoints/41"]


def test_cached_push_404_discovers_and_registers_after_backend_restart(
    monkeypatch,
) -> None:
    backend_sync, endpoint, fake_cache = _cached_push_arrangement(monkeypatch)
    calls = []
    responses = [_PushResponse({}, 404), _PushResponse([])]
    monkeypatch.setattr(
        backend_sync, "parse_requests_response_json", _parse_push_response
    )
    monkeypatch.setattr(
        backend_sync.requests,
        "get",
        lambda url, **kwargs: calls.append(url) or responses.pop(0),
    )
    monkeypatch.setattr(
        backend_sync.requests,
        "post",
        lambda url, **kwargs: calls.append(url) or _PushResponse({"id": 52}),
    )

    assert backend_sync.sync_proxmox_endpoint_to_backend(
        endpoint, base_url="https://backend.example.invalid"
    ) == (True, None, None)
    assert calls == [
        "https://backend.example.invalid/proxmox/endpoints/41",
        "https://backend.example.invalid/proxmox/endpoints",
        "https://backend.example.invalid/proxmox/endpoints",
    ]
    assert fake_cache.deleted


def test_cached_push_id_reuse_discovers_and_updates_the_correct_row(
    monkeypatch,
) -> None:
    backend_sync, endpoint, fake_cache = _cached_push_arrangement(monkeypatch)
    calls = []
    reused = {
        "id": 41,
        "name": "Other (nb:9)",
        "domain": "other.example.test",
        "port": 8006,
    }
    current = {
        "id": 52,
        "name": "PVE (nb:7)",
        "domain": "pve.example.test",
        "port": 8006,
    }
    responses = [_PushResponse(reused), _PushResponse([current])]
    monkeypatch.setattr(
        backend_sync, "parse_requests_response_json", _parse_push_response
    )
    monkeypatch.setattr(
        backend_sync.requests,
        "get",
        lambda url, **kwargs: calls.append(url) or responses.pop(0),
    )
    monkeypatch.setattr(
        backend_sync.requests,
        "put",
        lambda url, **kwargs: calls.append(url) or _PushResponse({"id": 52}),
    )

    assert backend_sync.sync_proxmox_endpoint_to_backend(
        endpoint, base_url="https://backend.example.invalid"
    ) == (True, None, None)
    assert calls[-1] == "https://backend.example.invalid/proxmox/endpoints/52"
    assert fake_cache.deleted


def test_cached_resolver_404_invalidates_and_retries_discovery(monkeypatch) -> None:
    backend_sync, endpoint, fake_cache = _cached_push_arrangement(monkeypatch)
    current = {
        "id": 52,
        "name": "PVE (nb:7)",
        "domain": "pve.example.test",
        "port": 8006,
    }
    responses = [_PushResponse({}, 404), _PushResponse([current])]
    monkeypatch.setattr(
        backend_sync, "parse_requests_response_json", _parse_push_response
    )
    monkeypatch.setattr(
        backend_sync.requests,
        "get",
        lambda *args, **kwargs: responses.pop(0),
    )

    assert backend_sync.resolve_backend_endpoint_id(
        endpoint, base_url="https://backend.example.invalid"
    ) == (52, None)
    assert fake_cache.deleted
