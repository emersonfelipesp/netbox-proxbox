"""Tests for test_individual_sync_service."""

from __future__ import annotations

import importlib
import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace

from tests.conftest import load_plugin_module


class _FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text
        self.url = "http://backend/sync/individual/vm"
        self.headers = {"Content-Type": "application/json"}

    def json(self):
        if isinstance(self._payload, BaseException):
            raise self._payload
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests

            raise requests.exceptions.HTTPError(
                f"HTTP {self.status_code}",
                response=self,
            )


def _load_individual_sync_module(monkeypatch):
    repo_root = Path(__file__).resolve().parents[1]

    netbox_module = types.ModuleType("netbox")
    netbox_plugins = types.ModuleType("netbox.plugins")
    netbox_plugins.PluginConfig = type("PluginConfig", (), {})
    monkeypatch.setitem(sys.modules, "netbox", netbox_module)
    monkeypatch.setitem(sys.modules, "netbox.plugins", netbox_plugins)

    nbp_root = types.ModuleType("netbox_proxbox")
    nbp_root.__path__ = [str(repo_root / "netbox_proxbox")]
    monkeypatch.setitem(sys.modules, "netbox_proxbox", nbp_root)

    nbp_services = types.ModuleType("netbox_proxbox.services")
    nbp_services.__path__ = [str(repo_root / "netbox_proxbox" / "services")]
    monkeypatch.setitem(sys.modules, "netbox_proxbox.services", nbp_services)

    nbp_views = types.ModuleType("netbox_proxbox.views")
    nbp_views.__path__ = [str(repo_root / "netbox_proxbox" / "views")]
    monkeypatch.setitem(sys.modules, "netbox_proxbox.views", nbp_views)

    models_stub = types.ModuleType("netbox_proxbox.models")
    models_stub.FastAPIEndpoint = type(
        "FastAPIEndpoint",
        (),
        {"objects": SimpleNamespace(first=lambda: None)},
    )
    monkeypatch.setitem(sys.modules, "netbox_proxbox.models", models_stub)

    utils_stub = types.ModuleType("netbox_proxbox.utils")
    utils_stub.get_fastapi_url = lambda obj: {}
    utils_stub.get_backend_auth_headers = lambda obj: {}
    utils_stub.get_first_fastapi_context = lambda: None
    monkeypatch.setitem(sys.modules, "netbox_proxbox.utils", utils_stub)

    sys.modules.pop("netbox_proxbox.services.individual_sync", None)
    sys.modules.pop("netbox_proxbox.views.error_utils", None)
    return importlib.import_module("netbox_proxbox.services.individual_sync")


def test_sync_individual_with_dependencies_propagates_cluster_context(monkeypatch):
    module = _load_individual_sync_module(monkeypatch)

    calls: list[tuple[str, dict]] = []

    def fake_sync(path, query_params=None, netbox_branch_schema_id=None):
        params = dict(query_params or {})
        calls.append((path, params))
        if path == "sync/individual/vm":
            return (
                {
                    "object_type": "vm",
                    "action": "updated",
                    "dependencies_synced": [
                        {"object_type": "node", "name": "pve01", "action": "created"}
                    ],
                },
                200,
            )
        return (
            {"object_type": "node", "action": "updated", "dependencies_synced": []},
            200,
        )

    monkeypatch.setattr(module, "sync_individual", fake_sync)

    _, status, _ = module.sync_individual_with_dependencies(
        "sync/individual/vm",
        {"cluster_name": "lab", "node": "pve01", "type": "qemu", "vmid": 101},
    )

    assert status == 200
    node_call = next(call for call in calls if call[0] == "sync/individual/node")
    assert node_call[1]["cluster_name"] == "lab"
    assert node_call[1]["node_name"] == "pve01"


def test_build_cache_key_is_deterministic(monkeypatch):
    module = _load_individual_sync_module(monkeypatch)

    key_a = module._build_cache_key(
        "sync/individual/vm", {"cluster_name": "lab", "node": "pve01", "vmid": 101}
    )
    key_b = module._build_cache_key(
        "sync/individual/vm", {"vmid": 101, "node": "pve01", "cluster_name": "lab"}
    )

    assert key_a == key_b


def test_sync_individual_reports_non_json_backend_response(monkeypatch):
    module = _load_individual_sync_module(monkeypatch)
    module.get_first_fastapi_context = lambda: {
        "http_url": "http://backend",
        "headers": {},
        "verify_ssl": True,
    }
    response = _FakeResponse(
        status_code=200,
        payload=json.JSONDecodeError("bad json", "<html>", 0),
        text="<html>not proxbox-api</html>",
    )
    monkeypatch.setattr(module.requests, "get", lambda *a, **kw: response)

    payload, status = module.sync_individual("sync/individual/vm", {"vmid": 101})

    assert status == 502
    assert "not valid JSON" in payload["error"]


def test_sync_individual_preserves_backend_http_status_and_detail(monkeypatch):
    module = _load_individual_sync_module(monkeypatch)
    module.get_first_fastapi_context = lambda: {
        "http_url": "http://backend",
        "headers": {},
        "verify_ssl": True,
    }
    response = _FakeResponse(status_code=404, payload={"detail": "VM not found"})
    monkeypatch.setattr(module.requests, "get", lambda *a, **kw: response)

    payload, status = module.sync_individual("sync/individual/vm", {"vmid": 999})

    assert status == 404
    assert payload["error"] == "VM not found"


def test_vm_sync_now_view_fails_fast_without_cluster(monkeypatch):
    services_pkg = types.ModuleType("netbox_proxbox.services")
    services_pkg.__path__ = []
    monkeypatch.setitem(sys.modules, "netbox_proxbox.services", services_pkg)
    service_stub = types.ModuleType("netbox_proxbox.services.individual_sync")
    service_stub.sync_individual_with_dependencies = lambda *args, **kwargs: (
        {},
        200,
        [],
    )
    monkeypatch.setitem(
        sys.modules, "netbox_proxbox.services.individual_sync", service_stub
    )

    module = load_plugin_module(
        "netbox_proxbox.views.sync_now.vm",
        monkeypatch=monkeypatch,
    )

    request = SimpleNamespace(user=SimpleNamespace(username="root"))
    vm = SimpleNamespace(
        name="vm-101",
        cluster=None,
        device=None,
        custom_field_data={"cf_proxmox_vm_id": 101, "cf_proxmox_vm_type": "qemu"},
        get_absolute_url=lambda: "/virtualization/virtual-machines/101/",
    )

    module.VirtualMachine.objects.get = lambda pk: vm

    called = {"count": 0}

    def fake_sync(*args, **kwargs):
        called["count"] += 1
        return {}, 200, []

    monkeypatch.setattr(module, "sync_individual_with_dependencies", fake_sync)

    response = module.VirtualMachineSyncNowView().post(request, pk=101)

    assert called["count"] == 0
    assert response.url == "/virtualization/virtual-machines/101/"
    assert any(
        "not linked to a Proxmox cluster" in msg for level, msg in module.messages.calls
    )


def test_storage_sync_now_view_fails_fast_without_cluster(monkeypatch):
    services_pkg = types.ModuleType("netbox_proxbox.services")
    services_pkg.__path__ = []
    monkeypatch.setitem(sys.modules, "netbox_proxbox.services", services_pkg)
    service_stub = types.ModuleType("netbox_proxbox.services.individual_sync")
    service_stub.sync_individual_with_dependencies = lambda *args, **kwargs: (
        {},
        200,
        [],
    )
    monkeypatch.setitem(
        sys.modules, "netbox_proxbox.services.individual_sync", service_stub
    )

    module = load_plugin_module(
        "netbox_proxbox.views.sync_now.storage",
        monkeypatch=monkeypatch,
    )

    request = SimpleNamespace(user=SimpleNamespace(username="root"))
    storage = SimpleNamespace(
        name="local-lvm",
        cluster=None,
        get_absolute_url=lambda: "/plugins/netbox-proxbox/storage/1/",
    )

    module.ProxmoxStorage.objects.get = lambda pk: storage

    called = {"count": 0}

    def fake_sync(*args, **kwargs):
        called["count"] += 1
        return {}, 200, []

    monkeypatch.setattr(module, "sync_individual_with_dependencies", fake_sync)

    response = module.ProxmoxStorageSyncNowView().post(request, pk=1)

    assert called["count"] == 0
    assert response.url == "/plugins/netbox-proxbox/storage/1/"
    assert any(
        "not linked to a Proxmox cluster" in msg for level, msg in module.messages.calls
    )
