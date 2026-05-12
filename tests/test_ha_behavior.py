"""Behaviour tests for the HA REST shim and HTML views.

The matching AST source contracts in ``test_api_ha.py``,
``test_views_ha.py``, and ``test_views_vm_ha.py`` pin module structure
(class names, registered URLs, error-message strings). Those guard
against accidental refactors. This file complements them with real
behaviour: load the modules with ``importlib`` + stubbed third-party
modules and exercise the actual code paths.

We patch ``requests.get`` to drive every error branch the modules can
take and verify the exact response shape (HTTP status, payload key,
template context detail string).
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
import requests

REPO_ROOT = Path(__file__).resolve().parents[1]


# ── Stubs: just enough rest_framework / drf_spectacular to import api/ha.py ──


class _StubResponse:
    """Minimal stand-in for ``rest_framework.response.Response``."""

    def __init__(self, data: Any = None, status: int = 200) -> None:
        self.data = data
        self.status_code = status


class _StubAPIView:
    """Stand-in for ``rest_framework.views.APIView``.

    Only used for class definition and inheritance checks; we call the
    ``get()`` methods directly with a ``SimpleNamespace`` request.
    """


def _install_drf_stubs(monkeypatch: pytest.MonkeyPatch) -> None:
    rest_framework = types.ModuleType("rest_framework")

    rest_framework_status = types.ModuleType("rest_framework.status")
    rest_framework_status.HTTP_200_OK = 200
    rest_framework_status.HTTP_502_BAD_GATEWAY = 502
    rest_framework_status.HTTP_503_SERVICE_UNAVAILABLE = 503

    rest_framework_request = types.ModuleType("rest_framework.request")
    rest_framework_request.Request = SimpleNamespace

    rest_framework_response = types.ModuleType("rest_framework.response")
    rest_framework_response.Response = _StubResponse

    rest_framework_views = types.ModuleType("rest_framework.views")
    rest_framework_views.APIView = _StubAPIView

    drf_spectacular = types.ModuleType("drf_spectacular")
    drf_spectacular_types = types.ModuleType("drf_spectacular.types")
    drf_spectacular_types.OpenApiTypes = SimpleNamespace(OBJECT="object")
    drf_spectacular_utils = types.ModuleType("drf_spectacular.utils")

    def _extend_schema(*_a: object, **_kw: object):
        def _decorator(func):
            return func

        return _decorator

    drf_spectacular_utils.extend_schema = _extend_schema

    monkeypatch.setitem(sys.modules, "rest_framework", rest_framework)
    monkeypatch.setitem(sys.modules, "rest_framework.status", rest_framework_status)
    monkeypatch.setitem(sys.modules, "rest_framework.request", rest_framework_request)
    monkeypatch.setitem(sys.modules, "rest_framework.response", rest_framework_response)
    monkeypatch.setitem(sys.modules, "rest_framework.views", rest_framework_views)
    monkeypatch.setitem(sys.modules, "drf_spectacular", drf_spectacular)
    monkeypatch.setitem(sys.modules, "drf_spectacular.types", drf_spectacular_types)
    monkeypatch.setitem(sys.modules, "drf_spectacular.utils", drf_spectacular_utils)


def _install_services_stubs(
    monkeypatch: pytest.MonkeyPatch,
    *,
    request_context: object | None,
) -> None:
    """Stub ``netbox_proxbox.services`` to bypass Django/NetBox dependencies."""
    services = types.ModuleType("netbox_proxbox.services")

    services_endpoint_errors = types.ModuleType(
        "netbox_proxbox.services._endpoint_errors"
    )
    services_endpoint_errors.translate_request_exception = lambda exc: str(exc)

    services_backend_context = types.ModuleType(
        "netbox_proxbox.services.backend_context"
    )
    services_backend_context.get_fastapi_request_context = lambda: request_context

    netbox_proxbox = types.ModuleType("netbox_proxbox")
    netbox_proxbox.__path__ = []  # mark as package

    monkeypatch.setitem(sys.modules, "netbox_proxbox", netbox_proxbox)
    monkeypatch.setitem(sys.modules, "netbox_proxbox.services", services)
    monkeypatch.setitem(
        sys.modules,
        "netbox_proxbox.services._endpoint_errors",
        services_endpoint_errors,
    )
    monkeypatch.setitem(
        sys.modules,
        "netbox_proxbox.services.backend_context",
        services_backend_context,
    )


def _load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _make_response(
    status_code: int, payload: Any = None, *, raises_on_json: bool = False
) -> Any:
    """Hand-rolled ``requests.Response``-like stub.

    Real ``requests.Response`` requires byte content + Content-Type to
    deserialize JSON; for unit tests we just need ``status_code``,
    ``ok``, and ``json()``.
    """

    class _Resp:
        def __init__(self) -> None:
            self.status_code = status_code
            self.ok = 200 <= status_code < 400

        def json(self) -> Any:
            if raises_on_json:
                raise ValueError("not json")
            return payload

    return _Resp()


# ── api/ha.py: _proxy_get behaviour ──────────────────────────────────────────


@pytest.fixture
def ha_api_module(monkeypatch: pytest.MonkeyPatch) -> Any:
    _install_drf_stubs(monkeypatch)
    _install_services_stubs(monkeypatch, request_context=None)
    return _load_module(
        "_netbox_proxbox_api_ha_under_test",
        REPO_ROOT / "netbox_proxbox" / "api" / "ha.py",
    )


def test_proxy_get_returns_payload_on_200(ha_api_module: Any) -> None:
    payload = {"status": {"quorate": True}, "groups": [], "resources": []}
    with patch("requests.get", return_value=_make_response(200, payload)):
        resp = ha_api_module._proxy_get(
            "http://api/proxmox/cluster/ha/summary",
            headers={"X-Test": "1"},
            verify=True,
            timeout=15,
        )
    assert resp.status_code == 200
    assert resp.data == payload


def test_proxy_get_translates_404_to_503_with_upgrade_hint(ha_api_module: Any) -> None:
    with patch("requests.get", return_value=_make_response(404)):
        resp = ha_api_module._proxy_get(
            "http://api/x", headers={}, verify=True, timeout=10
        )
    assert resp.status_code == 503
    assert "upgrade proxbox-api to v0.0.11 or later" in resp.data["detail"]


def test_proxy_get_returns_502_on_non_ok_status(ha_api_module: Any) -> None:
    with patch("requests.get", return_value=_make_response(500)):
        resp = ha_api_module._proxy_get(
            "http://api/x", headers={}, verify=True, timeout=10
        )
    assert resp.status_code == 502
    assert "500" in resp.data["detail"]


def test_proxy_get_returns_502_on_invalid_json(ha_api_module: Any) -> None:
    with patch(
        "requests.get",
        return_value=_make_response(200, raises_on_json=True),
    ):
        resp = ha_api_module._proxy_get(
            "http://api/x", headers={}, verify=True, timeout=10
        )
    assert resp.status_code == 502
    assert "Invalid HA payload" in resp.data["detail"]


def test_proxy_get_returns_502_on_request_exception(ha_api_module: Any) -> None:
    with patch(
        "requests.get",
        side_effect=requests.exceptions.ConnectionError("refused"),
    ):
        resp = ha_api_module._proxy_get(
            "http://api/x", headers={}, verify=True, timeout=10
        )
    assert resp.status_code == 502
    assert "refused" in resp.data["detail"]


# ── api/ha.py: APIView.get() behaviour without backend configured ────────────


def test_summary_view_returns_503_when_backend_unconfigured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_drf_stubs(monkeypatch)
    _install_services_stubs(monkeypatch, request_context=None)
    module = _load_module(
        "_netbox_proxbox_api_ha_under_test_unconfigured_summary",
        REPO_ROOT / "netbox_proxbox" / "api" / "ha.py",
    )
    view = module.HAClusterSummaryAPIView()
    resp = view.get(SimpleNamespace())
    assert resp.status_code == 503
    assert resp.data["detail"] == "No FastAPI backend endpoint is configured."


def test_vm_view_returns_503_when_backend_unconfigured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_drf_stubs(monkeypatch)
    _install_services_stubs(monkeypatch, request_context=None)
    module = _load_module(
        "_netbox_proxbox_api_ha_under_test_unconfigured_vm",
        REPO_ROOT / "netbox_proxbox" / "api" / "ha.py",
    )
    view = module.HAVMResourceAPIView()
    resp = view.get(SimpleNamespace(), 100)
    assert resp.status_code == 503


def test_summary_view_proxies_with_backend_url(monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = SimpleNamespace(http_url="http://api", headers={"a": "b"}, verify_ssl=True)
    _install_drf_stubs(monkeypatch)
    _install_services_stubs(monkeypatch, request_context=ctx)
    module = _load_module(
        "_netbox_proxbox_api_ha_under_test_summary_proxy",
        REPO_ROOT / "netbox_proxbox" / "api" / "ha.py",
    )
    view = module.HAClusterSummaryAPIView()
    payload = {"resources": [{"sid": "vm:101", "state": "started"}]}
    with patch("requests.get", return_value=_make_response(200, payload)) as mock_get:
        resp = view.get(SimpleNamespace())
    assert resp.status_code == 200
    assert resp.data == payload
    args, kwargs = mock_get.call_args
    assert args[0] == "http://api/proxmox/cluster/ha/summary"
    assert kwargs["headers"] == {"a": "b"}
    assert kwargs["verify"] is True
    assert kwargs["timeout"] == 15


def test_vm_view_normalises_null_payload_to_empty_dict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If proxbox-api returns ``null`` (no HA record), expose ``{}``."""
    ctx = SimpleNamespace(http_url="http://api", headers={}, verify_ssl=False)
    _install_drf_stubs(monkeypatch)
    _install_services_stubs(monkeypatch, request_context=ctx)
    module = _load_module(
        "_netbox_proxbox_api_ha_under_test_vm_null",
        REPO_ROOT / "netbox_proxbox" / "api" / "ha.py",
    )
    view = module.HAVMResourceAPIView()
    with patch("requests.get", return_value=_make_response(200, None)):
        resp = view.get(SimpleNamespace(), 4242)
    assert resp.status_code == 200
    assert resp.data == {}


def test_vm_view_uses_ten_second_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = SimpleNamespace(http_url="http://api", headers={}, verify_ssl=False)
    _install_drf_stubs(monkeypatch)
    _install_services_stubs(monkeypatch, request_context=ctx)
    module = _load_module(
        "_netbox_proxbox_api_ha_under_test_vm_timeout",
        REPO_ROOT / "netbox_proxbox" / "api" / "ha.py",
    )
    view = module.HAVMResourceAPIView()
    with patch("requests.get", return_value=_make_response(200, {})) as mock_get:
        view.get(SimpleNamespace(), 4242)
    assert mock_get.call_args.kwargs["timeout"] == 10


# ── views/vm_ha.py: _extract_vmid (pure, importable helper) ──────────────────


@pytest.fixture
def vm_ha_module(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Load views/vm_ha.py with enough Django/NetBox stubs to import.

    Only ``_extract_vmid`` is exercised directly; the surrounding view
    decorators are tolerated via stubs.
    """
    django = types.ModuleType("django")
    django_http = types.ModuleType("django.http")
    django_http.HttpRequest = SimpleNamespace
    monkeypatch.setitem(sys.modules, "django", django)
    monkeypatch.setitem(sys.modules, "django.http", django_http)

    netbox = types.ModuleType("netbox")
    netbox_views = types.ModuleType("netbox.views")
    netbox_views_generic = types.ModuleType("netbox.views.generic")

    class _ObjectView:
        pass

    netbox_views_generic.ObjectView = _ObjectView
    netbox_views.generic = netbox_views_generic
    monkeypatch.setitem(sys.modules, "netbox", netbox)
    monkeypatch.setitem(sys.modules, "netbox.views", netbox_views)
    monkeypatch.setitem(sys.modules, "netbox.views.generic", netbox_views_generic)

    utilities = types.ModuleType("utilities")
    utilities_views = types.ModuleType("utilities.views")

    class _ViewTab:
        def __init__(self, **kwargs: object) -> None:
            self.__dict__.update(kwargs)

    def _register_model_view(*_a: object, **_kw: object):
        def _decorator(cls):
            return cls

        return _decorator

    utilities_views.ViewTab = _ViewTab
    utilities_views.register_model_view = _register_model_view
    monkeypatch.setitem(sys.modules, "utilities", utilities)
    monkeypatch.setitem(sys.modules, "utilities.views", utilities_views)

    virtualization = types.ModuleType("virtualization")
    virtualization_models = types.ModuleType("virtualization.models")

    class _VirtualMachine:
        objects = SimpleNamespace(all=lambda: None, restrict=lambda *_a, **_kw: None)

    virtualization_models.VirtualMachine = _VirtualMachine
    monkeypatch.setitem(sys.modules, "virtualization", virtualization)
    monkeypatch.setitem(sys.modules, "virtualization.models", virtualization_models)

    _install_services_stubs(monkeypatch, request_context=None)

    return _load_module(
        "_netbox_proxbox_vm_ha_under_test",
        REPO_ROOT / "netbox_proxbox" / "views" / "vm_ha.py",
    )


@pytest.mark.parametrize(
    ("custom_fields", "expected"),
    [
        ({}, None),
        ({"proxmox_vm_id": None}, None),
        ({"proxmox_vm_id": ""}, None),
        ({"proxmox_vm_id": "abc"}, None),
        ({"proxmox_vm_id": 100}, 100),
        ({"proxmox_vm_id": "100"}, 100),
        ({"cf_proxmox_vm_id": "200"}, 200),
        ({"proxmox_vm_id": "300", "cf_proxmox_vm_id": "999"}, 300),
    ],
)
def test_extract_vmid_handles_all_input_shapes(
    vm_ha_module: Any, custom_fields: dict[str, object], expected: int | None
) -> None:
    vm = SimpleNamespace(custom_field_data=custom_fields)
    assert vm_ha_module._extract_vmid(vm) == expected


def test_extract_vmid_returns_none_when_attribute_missing(vm_ha_module: Any) -> None:
    """A VM without ``custom_field_data`` should return None, not raise."""
    vm = SimpleNamespace()
    assert vm_ha_module._extract_vmid(vm) is None


def test_extract_vmid_returns_none_when_custom_field_data_is_none(
    vm_ha_module: Any,
) -> None:
    vm = SimpleNamespace(custom_field_data=None)
    assert vm_ha_module._extract_vmid(vm) is None
