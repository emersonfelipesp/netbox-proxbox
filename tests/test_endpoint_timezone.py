"""Focused behavior tests for best-effort endpoint timezone discovery."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests


REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def endpoint_timezone(monkeypatch):
    """Load the service with its Django/NetBox-owned dependencies stubbed."""
    package = types.ModuleType("netbox_proxbox")
    package.__path__ = [str(REPO_ROOT / "netbox_proxbox")]
    monkeypatch.setitem(sys.modules, "netbox_proxbox", package)
    services = types.ModuleType("netbox_proxbox.services")
    services.__path__ = [str(REPO_ROOT / "netbox_proxbox" / "services")]
    monkeypatch.setitem(sys.modules, "netbox_proxbox.services", services)

    django = types.ModuleType("django")
    django.__path__ = []
    django_db = types.ModuleType("django.db")
    django_db.DatabaseError = type("DatabaseError", (Exception,), {})
    monkeypatch.setitem(sys.modules, "django", django)
    monkeypatch.setitem(sys.modules, "django.db", django_db)

    backend_context = types.ModuleType("netbox_proxbox.services.backend_context")
    backend_context.get_fastapi_request_context = lambda **kwargs: None
    monkeypatch.setitem(
        sys.modules, "netbox_proxbox.services.backend_context", backend_context
    )
    views = types.ModuleType("netbox_proxbox.views")
    views.__path__ = [str(REPO_ROOT / "netbox_proxbox" / "views")]
    monkeypatch.setitem(sys.modules, "netbox_proxbox.views", views)
    backend_sync = types.ModuleType("netbox_proxbox.views.backend_sync")
    backend_sync.proxmox_backend_name = lambda endpoint: (
        f"{endpoint.name} (nb:{endpoint.pk})"
    )
    monkeypatch.setitem(sys.modules, "netbox_proxbox.views.backend_sync", backend_sync)

    module_name = "netbox_proxbox.services.endpoint_timezone"
    spec = importlib.util.spec_from_file_location(
        module_name,
        REPO_ROOT / "netbox_proxbox" / "services" / "endpoint_timezone.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, module_name, module)
    spec.loader.exec_module(module)
    return module


class _NodeQuery:
    def __init__(self, value: object) -> None:
        self.value = value
        self.ordering: tuple[str, ...] | None = None

    def order_by(self, *fields: str) -> _NodeQuery:
        self.ordering = fields
        return self

    def values_list(self, field: str, *, flat: bool) -> _NodeQuery:
        assert (field, flat) == ("name", True)
        return self

    def first(self) -> object:
        return self.value


class _UpdateQuery:
    def __init__(self, manager: _Manager) -> None:
        self.manager = manager

    def update(self, **values: object) -> int:
        self.manager.update_values = values
        return self.manager.update_count


class _Manager:
    def __init__(self, update_count: int = 1) -> None:
        self.update_count = update_count
        self.filtered_pk: int | None = None
        self.update_values: dict[str, object] | None = None

    def filter(self, *, pk: int) -> _UpdateQuery:
        self.filtered_pk = pk
        return _UpdateQuery(self)


def _endpoint(*, node: object = "pve-01", enabled: bool = True) -> object:
    manager = _Manager()
    endpoint_type = type("Endpoint", (), {"objects": manager})
    value = endpoint_type()
    value.pk = 37
    value.name = "Primary"
    value.enabled = enabled
    value.proxmox_nodes = _NodeQuery(node)
    value._manager = manager
    return value


def _context() -> SimpleNamespace:
    return SimpleNamespace(
        http_url="https://backend.example/",
        headers={"X-Proxbox-API-Key": "test-key"},
        verify_ssl=True,
    )


def _response(payload: object, *, status_error: Exception | None = None) -> Mock:
    response = Mock()
    response.json.return_value = payload
    response.raise_for_status.side_effect = status_error
    return response


def test_discovery_uses_generated_get_route_and_approved_context(
    endpoint_timezone, monkeypatch
) -> None:
    endpoint = _endpoint(node="pve node/1")
    context_calls: list[int | None] = []
    get = Mock(return_value=_response({"timezone": "America/Sao_Paulo"}))
    monkeypatch.setattr(
        endpoint_timezone,
        "get_fastapi_request_context",
        lambda *, endpoint_id=None: context_calls.append(endpoint_id) or _context(),
    )
    monkeypatch.setattr(endpoint_timezone.requests, "get", get)

    result = endpoint_timezone.discover_endpoint_timezone(
        endpoint, fastapi_endpoint_id=9, timeout=999
    )

    assert result == "America/Sao_Paulo"
    assert context_calls == [9]
    assert endpoint.proxmox_nodes.ordering == ("-online", "-local", "pk")
    get.assert_called_once_with(
        "https://backend.example/proxmox/api2/nodes/pve%20node%2F1/time",
        params={"source": "database", "target_name": "Primary (nb:37)"},
        headers={"X-Proxbox-API-Key": "test-key"},
        verify=True,
        timeout=endpoint_timezone.ENDPOINT_TIMEZONE_TIMEOUT,
        allow_redirects=False,
    )


def test_refresh_persists_with_queryset_update_without_save(
    endpoint_timezone, monkeypatch
) -> None:
    endpoint = _endpoint()
    monkeypatch.setattr(
        endpoint_timezone,
        "discover_endpoint_timezone",
        lambda *args, **kwargs: "Europe/Lisbon",
    )

    assert endpoint_timezone.refresh_endpoint_timezone(endpoint) is True
    assert endpoint._manager.filtered_pk == 37
    assert endpoint._manager.update_values == {"iana_timezone": "Europe/Lisbon"}


def test_discovery_is_network_free_when_disabled_or_missing_node(
    endpoint_timezone, monkeypatch
) -> None:
    get = Mock()
    context = Mock()
    monkeypatch.setattr(endpoint_timezone.requests, "get", get)
    monkeypatch.setattr(endpoint_timezone, "get_fastapi_request_context", context)

    assert (
        endpoint_timezone.discover_endpoint_timezone(_endpoint(enabled=False)) is None
    )
    assert endpoint_timezone.discover_endpoint_timezone(_endpoint(node=None)) is None
    get.assert_not_called()
    context.assert_not_called()


def test_discovery_fails_open_for_unavailable_backend(
    endpoint_timezone, monkeypatch
) -> None:
    monkeypatch.setattr(
        endpoint_timezone, "get_fastapi_request_context", lambda **kwargs: None
    )
    get = Mock()
    monkeypatch.setattr(endpoint_timezone.requests, "get", get)

    assert endpoint_timezone.discover_endpoint_timezone(_endpoint()) is None
    get.assert_not_called()


def test_discovery_fails_open_for_transport_status_and_json_errors(
    endpoint_timezone, monkeypatch
) -> None:
    monkeypatch.setattr(
        endpoint_timezone, "get_fastapi_request_context", lambda **kwargs: _context()
    )
    failures = (
        requests.ConnectionError("unavailable"),
        requests.HTTPError("rejected"),
        ValueError("invalid json"),
    )
    for failure in failures:
        response = _response({"timezone": "UTC"})
        if isinstance(failure, ValueError):
            response.json.side_effect = failure
        else:
            response.raise_for_status.side_effect = failure
        monkeypatch.setattr(
            endpoint_timezone.requests, "get", Mock(return_value=response)
        )
        assert endpoint_timezone.discover_endpoint_timezone(_endpoint()) is None


def test_discovery_rejects_malformed_or_non_iana_payloads(
    endpoint_timezone, monkeypatch
) -> None:
    monkeypatch.setattr(
        endpoint_timezone, "get_fastapi_request_context", lambda **kwargs: _context()
    )
    invalid_payloads = (
        [],
        {},
        {"timezone": 42},
        {"timezone": "../etc/passwd"},
        {"timezone": "Not/A_Real_Zone"},
        {"timezone": "A" * 65},
    )
    for payload in invalid_payloads:
        monkeypatch.setattr(
            endpoint_timezone.requests, "get", Mock(return_value=_response(payload))
        )
        assert endpoint_timezone.discover_endpoint_timezone(_endpoint()) is None


def test_refresh_does_not_overwrite_on_failed_discovery(
    endpoint_timezone, monkeypatch
) -> None:
    endpoint = _endpoint()
    monkeypatch.setattr(
        endpoint_timezone, "discover_endpoint_timezone", lambda *args, **kwargs: None
    )

    assert endpoint_timezone.refresh_endpoint_timezone(endpoint) is False
    assert endpoint._manager.filtered_pk is None
    assert endpoint._manager.update_values is None
