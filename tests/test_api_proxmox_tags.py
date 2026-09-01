"""Tests for plugin REST proxmox-tags endpoints.

``netbox_proxbox.api.proxmox_tags`` is not loadable through
``conftest.load_plugin_module`` (that helper targets ``views.*`` only), so this
module path-loads the API file against compact stubs — same technique as
``test_job_cancel_api_behavior.py``.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PROXMOX_TAGS_API = REPO_ROOT / "netbox_proxbox" / "api" / "proxmox_tags.py"


def _load(monkeypatch: pytest.MonkeyPatch):
    requests_mod = types.ModuleType("requests")
    requests_exceptions = types.ModuleType("requests.exceptions")

    class RequestException(Exception):
        pass

    requests_exceptions.RequestException = RequestException
    requests_mod.exceptions = requests_exceptions
    requests_mod.request = lambda *a, **kw: None

    endpoint_errors_mod = types.ModuleType("netbox_proxbox.services._endpoint_errors")
    endpoint_errors_mod.translate_request_exception = lambda exc: str(exc)

    backend_context_mod = types.ModuleType("netbox_proxbox.services.backend_context")
    backend_context_mod.get_fastapi_request_context = lambda endpoint_id=None: None

    operational_mod = types.ModuleType("netbox_proxbox.views.operational")
    operational_mod.resolve_vm_endpoint_context = lambda vm: (7, 100, "qemu")
    operational_mod._current_node_name = lambda vm: "pve1"

    proxbox_access_mod = types.ModuleType("netbox_proxbox.views.proxbox_access")
    proxbox_access_mod.permission_run_proxmox_action = lambda: "core.run_proxmox_action"

    utils_mod = types.ModuleType("netbox_proxbox.utils")
    utils_mod.resolve_vm_type = lambda vm: "qemu"

    rf = types.ModuleType("rest_framework")
    rf_status = types.ModuleType("rest_framework.status")
    rf_status.HTTP_200_OK = 200
    rf_status.HTTP_400_BAD_REQUEST = 400
    rf_status.HTTP_403_FORBIDDEN = 403
    rf_status.HTTP_404_NOT_FOUND = 404
    rf_status.HTTP_422_UNPROCESSABLE_ENTITY = 422
    rf_status.HTTP_502_BAD_GATEWAY = 502
    rf_status.HTTP_503_SERVICE_UNAVAILABLE = 503

    class _Response:
        def __init__(self, data, status=200):
            self.data = data
            self.status_code = status

    rf_response = types.ModuleType("rest_framework.response")
    rf_response.Response = _Response

    class _APIView:
        pass

    rf_views = types.ModuleType("rest_framework.views")
    rf_views.APIView = _APIView

    rf_request = types.ModuleType("rest_framework.request")
    rf_request.Request = object

    drf_spectacular = types.ModuleType("drf_spectacular")
    drf_spectacular_types = types.ModuleType("drf_spectacular.types")
    drf_spectacular_types.OpenApiTypes = SimpleNamespace(OBJECT=object)
    drf_spectacular_utils = types.ModuleType("drf_spectacular.utils")
    drf_spectacular_utils.extend_schema = lambda *a, **kw: lambda fn: fn

    virtualization_models = types.ModuleType("virtualization.models")

    class _VirtualMachine:
        DoesNotExist = type("DoesNotExist", (Exception,), {})
        objects = SimpleNamespace()

    virtualization_models.VirtualMachine = _VirtualMachine

    for name, mod in {
        "requests": requests_mod,
        "requests.exceptions": requests_exceptions,
        "netbox_proxbox.services._endpoint_errors": endpoint_errors_mod,
        "netbox_proxbox.services.backend_context": backend_context_mod,
        "netbox_proxbox.views.operational": operational_mod,
        "netbox_proxbox.views.proxbox_access": proxbox_access_mod,
        "netbox_proxbox.utils": utils_mod,
        "rest_framework": rf,
        "rest_framework.status": rf_status,
        "rest_framework.response": rf_response,
        "rest_framework.views": rf_views,
        "rest_framework.request": rf_request,
        "drf_spectacular": drf_spectacular,
        "drf_spectacular.types": drf_spectacular_types,
        "drf_spectacular.utils": drf_spectacular_utils,
        "virtualization.models": virtualization_models,
    }.items():
        monkeypatch.setitem(sys.modules, name, mod)

    spec = importlib.util.spec_from_file_location(
        "netbox_proxbox.api.proxmox_tags",
        PROXMOX_TAGS_API,
    )
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "netbox_proxbox.api.proxmox_tags", module)
    spec.loader.exec_module(module)
    return module


def _make_vm(*, pk=42):
    return SimpleNamespace(
        pk=pk, cluster=SimpleNamespace(), device=None, custom_field_data={}
    )


def _request(*, data: dict, has_perm: bool = True):
    return SimpleNamespace(
        user=SimpleNamespace(
            has_perm=lambda perm: (
                has_perm if perm == "core.run_proxmox_action" else False
            ),
            get_username=lambda: "alice",
        ),
        data=data,
    )


def test_put_forwards_replace_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load(monkeypatch)
    vm = _make_vm()
    captured: dict[str, object] = {}

    class _Manager:
        def restrict(self, _user, _action):
            return self

        def select_related(self, *_args, **_kwargs):
            return self

        def get(self, pk):
            assert pk == vm.pk
            return vm

    module.VirtualMachine = SimpleNamespace(objects=_Manager(), DoesNotExist=Exception)

    def fake_request(
        method,
        url,
        params=None,
        json=None,
        headers=None,
        timeout=None,
        verify=None,
        allow_redirects=True,
    ):
        captured["method"] = method
        captured["url"] = url
        captured["params"] = params
        captured["json"] = json
        captured["headers"] = dict(headers or {})
        return SimpleNamespace(
            ok=True,
            status_code=200,
            json=lambda: {
                "ok": True,
                "vmid": 100,
                "vm_type": "qemu",
                "endpoint_id": 7,
                "node": "pve1",
                "tags_after": ["alpha"],
            },
        )

    monkeypatch.setattr(module.requests, "request", fake_request)
    monkeypatch.setattr(
        module,
        "get_fastapi_request_context",
        lambda endpoint_id=None: SimpleNamespace(
            http_url="https://backend.example.com:8800",
            headers={"X-Proxbox-API-Key": "secret"},
            verify_ssl=False,
        ),
    )

    response = module.VirtualMachineProxmoxTagsAPIView().put(
        _request(data={"tags": ["alpha"]}),
        pk=vm.pk,
    )

    assert response.status_code == 200
    assert captured["method"] == "PUT"
    assert captured["url"] == "https://backend.example.com:8800/proxmox/qemu/100/tags"
    assert captured["params"] == {"endpoint_id": 7}
    assert captured["json"] == {"node": "pve1", "tags": ["alpha"]}
    assert captured["headers"]["X-Proxbox-Actor"] == "alice"


def test_patch_rejects_missing_add_and_remove(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load(monkeypatch)
    vm = _make_vm()

    class _Manager:
        def restrict(self, _user, _action):
            return self

        def select_related(self, *_args, **_kwargs):
            return self

        def get(self, pk):
            return vm

    module.VirtualMachine = SimpleNamespace(objects=_Manager(), DoesNotExist=Exception)

    response = module.VirtualMachineProxmoxTagsAPIView().patch(
        _request(data={}),
        pk=vm.pk,
    )

    assert response.status_code == 400
    assert response.data["reason"] == "invalid_payload"
