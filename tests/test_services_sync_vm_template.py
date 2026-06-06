"""Behavior tests for ``services.sync_vm_template.sync_vm_templates``.

The service normally depends on Django ORM models, transaction management, and
proxbox-api HTTP calls. These tests load it with small in-memory stubs so the
two-phase sync behavior can be exercised without a NetBox runtime.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _Template:
    def __init__(
        self,
        *,
        pk: int,
        proxmox_endpoint: object,
        vmid: int,
        proxmox_type: str = "qemu",
        bootstrap_only: bool = False,
        name: str = "",
        **extra,
    ):
        self.pk = pk
        self.proxmox_endpoint = proxmox_endpoint
        self.vmid = vmid
        self.proxmox_type = proxmox_type
        self.bootstrap_only = bootstrap_only
        self.name = name or f"template-{vmid}"
        for key, value in extra.items():
            setattr(self, key, value)

    def save(self, update_fields=None):
        self.saved_update_fields = update_fields


class _TemplateQuerySet:
    def __init__(self, manager, items):
        self.manager = manager
        self.items = list(items)

    def __iter__(self):
        return iter(self.items)

    def first(self):
        return self.items[0] if self.items else None

    def values_list(self, *fields):
        return [tuple(getattr(item, field) for field in fields) for item in self.items]

    def delete(self):
        deleted = 0
        for item in list(self.items):
            if item in self.manager.items:
                self.manager.items.remove(item)
                deleted += 1
        return deleted, {}


class _TemplateManager:
    def __init__(self, endpoint):
        self.endpoint = endpoint
        self.items = [
            _Template(pk=1, proxmox_endpoint=endpoint, vmid=101),
            _Template(
                pk=2,
                proxmox_endpoint=endpoint,
                vmid=102,
                bootstrap_only=True,
            ),
        ]
        self.next_pk = 3

    def filter(self, **kwargs):
        items = list(self.items)
        if "proxmox_endpoint" in kwargs:
            items = [
                item
                for item in items
                if item.proxmox_endpoint is kwargs["proxmox_endpoint"]
            ]
        if "vmid" in kwargs:
            items = [item for item in items if item.vmid == kwargs["vmid"]]
        if "pk__in" in kwargs:
            ids = set(kwargs["pk__in"])
            items = [item for item in items if item.pk in ids]
        return _TemplateQuerySet(self, items)

    def create(self, **kwargs):
        template = _Template(pk=self.next_pk, **kwargs)
        self.next_pk += 1
        self.items.append(template)
        return template


@pytest.fixture
def sync_vm_template_module(monkeypatch):
    pkg = types.ModuleType("netbox_proxbox")
    pkg.__path__ = [str(REPO_ROOT / "netbox_proxbox")]
    monkeypatch.setitem(sys.modules, "netbox_proxbox", pkg)

    choices = types.ModuleType("netbox_proxbox.choices")
    choices.SyncModeChoices = SimpleNamespace(
        ALWAYS="always",
        BOOTSTRAP_ONLY="bootstrap_only",
        DISABLED="disabled",
    )
    monkeypatch.setitem(sys.modules, "netbox_proxbox.choices", choices)

    class _DoesNotExist(Exception):
        pass

    endpoint = SimpleNamespace(
        pk=1,
        name="pve-1",
        effective_sync_mode=lambda resource_type: "always",
    )
    endpoint.__str__ = lambda self=endpoint: "pve-1"

    class _EndpointManager:
        def get(self, **kwargs):
            if kwargs.get("pk") == 1:
                return endpoint
            raise _DoesNotExist()

    class _ProxmoxEndpoint:
        DoesNotExist = _DoesNotExist
        objects = _EndpointManager()

    class _EmptyQuerySet:
        def filter(self, **_kwargs):
            return self

        def first(self):
            return None

    class _RelatedManager:
        def filter(self, **_kwargs):
            return _EmptyQuerySet()

    template_manager = _TemplateManager(endpoint)

    class _ProxmoxVMTemplate:
        objects = template_manager

    models = types.ModuleType("netbox_proxbox.models")
    models.ProxmoxEndpoint = _ProxmoxEndpoint
    models.ProxmoxCluster = SimpleNamespace(objects=_RelatedManager())
    models.ProxmoxNode = SimpleNamespace(objects=_RelatedManager())
    models.ProxmoxVMTemplate = _ProxmoxVMTemplate
    monkeypatch.setitem(sys.modules, "netbox_proxbox.models", models)

    services_pkg = types.ModuleType("netbox_proxbox.services")
    monkeypatch.setitem(sys.modules, "netbox_proxbox.services", services_pkg)
    backend_proxy = types.ModuleType("netbox_proxbox.services.backend_proxy")
    backend_proxy.get_fastapi_request_context = lambda: None
    monkeypatch.setitem(
        sys.modules, "netbox_proxbox.services.backend_proxy", backend_proxy
    )

    views_pkg = types.ModuleType("netbox_proxbox.views")
    monkeypatch.setitem(sys.modules, "netbox_proxbox.views", views_pkg)
    backend_sync = types.ModuleType("netbox_proxbox.views.backend_sync")
    backend_sync.resolve_backend_endpoint_id = lambda *args, **kwargs: (99, None)
    monkeypatch.setitem(sys.modules, "netbox_proxbox.views.backend_sync", backend_sync)

    sync_stages = types.ModuleType("netbox_proxbox.sync_stages")
    sync_stages._add_bootstrap_only_tag = lambda obj: setattr(
        obj, "bootstrap_only", True
    )
    sync_stages._has_bootstrap_only_tag = lambda obj: bool(
        getattr(obj, "bootstrap_only", False)
    )
    sync_stages._bootstrap_only_should_skip_existing = (
        lambda obj, mode: mode == "bootstrap_only"
        and sync_stages._has_bootstrap_only_tag(obj)
    )
    monkeypatch.setitem(sys.modules, "netbox_proxbox.sync_stages", sync_stages)

    django_pkg = types.ModuleType("django")
    django_pkg.__path__ = []
    monkeypatch.setitem(sys.modules, "django", django_pkg)
    db_mod = types.ModuleType("django.db")
    atomic_state = {"in_atomic": False}

    class _Atomic:
        def __enter__(self):
            atomic_state["in_atomic"] = True
            return self

        def __exit__(self, *_args):
            atomic_state["in_atomic"] = False
            return False

    db_mod.transaction = SimpleNamespace(atomic=lambda: _Atomic())
    monkeypatch.setitem(sys.modules, "django.db", db_mod)

    django_utils = types.ModuleType("django.utils")
    django_utils.__path__ = []
    timezone_mod = types.ModuleType("django.utils.timezone")
    timezone_mod.now = lambda: "now"
    django_utils.timezone = timezone_mod
    monkeypatch.setitem(sys.modules, "django.utils", django_utils)
    monkeypatch.setitem(sys.modules, "django.utils.timezone", timezone_mod)

    sys.modules.pop("netbox_proxbox.services.sync_vm_template", None)
    spec = importlib.util.spec_from_file_location(
        "netbox_proxbox.services.sync_vm_template",
        REPO_ROOT / "netbox_proxbox" / "services" / "sync_vm_template.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["netbox_proxbox.services.sync_vm_template"] = module
    spec.loader.exec_module(module)
    module._atomic_state = atomic_state
    module._template_manager = template_manager
    return module


def test_sync_vm_templates_fetches_config_before_atomic_and_deletes_stale(
    sync_vm_template_module,
    monkeypatch,
):
    http_calls: list[tuple[str, bool]] = []

    resources_payload = [
        {
            "pve-cluster": [
                {
                    "type": "qemu",
                    "vmid": 100,
                    "template": 1,
                    "node": "pve01",
                    "name": "ubuntu-template",
                    "maxcpu": 2,
                    "maxmem": 1024 * 1024 * 1024,
                    "maxdisk": 10 * 1024 * 1024 * 1024,
                    "status": "stopped",
                }
            ]
        }
    ]
    config_payload = {
        "cores": 2,
        "memory": 1024,
        "ostype": "l26",
        "net0": "virtio=AA:BB:CC:DD:EE:FF,bridge=vmbr0",
        "scsi0": "local-lvm:vm-100-disk-0",
        "description": "golden image",
    }

    def fake_get(url, **_kwargs):
        in_atomic = sync_vm_template_module._atomic_state["in_atomic"]
        http_calls.append((url, in_atomic))
        assert not in_atomic, f"HTTP call happened inside transaction.atomic(): {url}"
        if url.endswith("/proxmox/cluster/resources"):
            return _Response(resources_payload)
        if url.endswith("/proxmox/pve01/qemu/100/config"):
            return _Response(config_payload)
        raise AssertionError(url)

    monkeypatch.setattr(sync_vm_template_module.requests, "get", fake_get)

    result = sync_vm_template_module.sync_vm_templates(
        endpoint_id=1,
        fastapi_url="http://backend:8000",
        auth_headers={"Authorization": "Bearer token"},
    )

    assert result.success is True
    assert result.templates_created == 1
    assert result.templates_deleted == 1
    assert all(not in_atomic for _url, in_atomic in http_calls)

    remaining = {
        (template.vmid, template.bootstrap_only)
        for template in sync_vm_template_module._template_manager.items
    }
    assert remaining == {
        (100, False),
        (102, True),
    }
