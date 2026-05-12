"""Tests for the operational-verb backend-proxy views (issue #376 sub-PR G).

Cover the §2.3 trust boundary on the plugin side:

* Each verb POST resolves ``(endpoint_id, vmid, vm_type)`` and forwards
  to proxbox-api with a fresh ``Idempotency-Key`` and the
  ``endpoint_id`` query param.
* Unresolvable VMs surface a Django message and redirect — never POST.
* Backend non-2xx is surfaced as ``messages.error`` with the
  proxbox-api ``reason`` field, if present.
* The migrate POST requires a ``target`` form value (400-equivalent
  flash + redirect back to picker).

The Django + utilities + requests modules are stubbed by
``load_plugin_module``; we replace ``requests.post`` with a recorder
so the test runs offline.
"""

from __future__ import annotations

import sys
import types
from types import SimpleNamespace

import pytest

from tests.conftest import load_plugin_module


def _stub_services_before_load(monkeypatch):
    """Stub services.* and ``requests`` modules so operational.py imports cleanly."""
    requests_mod = types.ModuleType("requests")
    requests_exceptions = types.ModuleType("requests.exceptions")

    class RequestException(Exception):
        pass

    requests_exceptions.RequestException = RequestException
    requests_mod.exceptions = requests_exceptions
    requests_mod.post = lambda *a, **kw: None
    requests_mod.Response = object
    monkeypatch.setitem(sys.modules, "requests", requests_mod)
    monkeypatch.setitem(sys.modules, "requests.exceptions", requests_exceptions)

    endpoint_errors_mod = types.ModuleType("netbox_proxbox.services._endpoint_errors")
    endpoint_errors_mod.translate_request_exception = lambda exc: str(exc)
    monkeypatch.setitem(
        sys.modules,
        "netbox_proxbox.services._endpoint_errors",
        endpoint_errors_mod,
    )

    backend_context_mod = types.ModuleType("netbox_proxbox.services.backend_context")
    backend_context_mod.get_fastapi_request_context = lambda endpoint_id=None: None
    monkeypatch.setitem(
        sys.modules,
        "netbox_proxbox.services.backend_context",
        backend_context_mod,
    )

    services_pkg = types.ModuleType("netbox_proxbox.services")
    services_pkg._endpoint_errors = endpoint_errors_mod
    services_pkg.backend_context = backend_context_mod
    monkeypatch.setitem(sys.modules, "netbox_proxbox.services", services_pkg)


def _make_vm(*, pk=42, vmid=100, endpoint_id=7, vm_type="qemu"):
    cluster = SimpleNamespace(
        proxmox_cluster_tracking=SimpleNamespace(
            first=lambda: SimpleNamespace(endpoint_id=endpoint_id)
        ),
    )
    return SimpleNamespace(
        pk=pk,
        name=f"vm-{pk}",
        cluster=cluster,
        custom_field_data={
            "proxmox_vm_id": vmid,
            "proxmox_vm_type": vm_type,
        },
        virtual_machine_type=None,
        device=None,
        get_absolute_url=lambda: f"/virtualization/virtual-machines/{pk}/",
    )


def _load(monkeypatch):
    _stub_services_before_load(monkeypatch)
    return load_plugin_module(
        "netbox_proxbox.views.operational",
        monkeypatch=monkeypatch,
    )


def _bind_vm(monkeypatch, operational, vm):
    """Make ``get_object_or_404`` return ``vm`` regardless of input."""
    monkeypatch.setattr(operational, "get_object_or_404", lambda *a, **kw: vm)


def _patch_backend(monkeypatch, operational, *, response):
    captured: dict[str, object] = {}

    def fake_post(url, params=None, json=None, headers=None, timeout=None, verify=None):
        captured["url"] = url
        captured["params"] = params or {}
        captured["json"] = json or {}
        captured["headers"] = dict(headers or {})
        captured["timeout"] = timeout
        captured["verify"] = verify
        return response

    monkeypatch.setattr(operational.requests, "post", fake_post)
    monkeypatch.setattr(
        operational,
        "get_fastapi_request_context",
        lambda endpoint_id=None: SimpleNamespace(
            http_url="https://backend.example.com:8800",
            headers={"X-Proxbox-API-Key": "secret"},
            verify_ssl=False,
        ),
    )
    return captured


def _fake_response(status_code=200, body=None):
    payload = body or {"ok": True}

    def _json():
        return payload

    return SimpleNamespace(status_code=status_code, json=_json)


# ---------- resolve_vm_endpoint_context ----------


def test_resolver_returns_triple_for_addressable_vm(monkeypatch):
    operational = _load(monkeypatch)
    vm = _make_vm()
    assert operational.resolve_vm_endpoint_context(vm) == (7, 100, "qemu")


def test_resolver_returns_none_without_cluster(monkeypatch):
    operational = _load(monkeypatch)
    vm = _make_vm()
    vm.cluster = None
    assert operational.resolve_vm_endpoint_context(vm) is None


def test_resolver_returns_none_without_endpoint_tracking(monkeypatch):
    operational = _load(monkeypatch)
    vm = _make_vm()
    vm.cluster.proxmox_cluster_tracking.first = lambda: None
    assert operational.resolve_vm_endpoint_context(vm) is None


def test_resolver_returns_none_without_vmid(monkeypatch):
    operational = _load(monkeypatch)
    vm = _make_vm()
    vm.custom_field_data = {}
    assert operational.resolve_vm_endpoint_context(vm) is None


# ---------- POST → backend forward ----------


@pytest.mark.parametrize(
    "view_attr,verb",
    [
        ("OperationalStartView", "start"),
        ("OperationalStopView", "stop"),
        ("OperationalSnapshotView", "snapshot"),
    ],
)
def test_verb_post_forwards_to_backend(monkeypatch, view_attr, verb):
    operational = _load(monkeypatch)
    vm = _make_vm()
    _bind_vm(monkeypatch, operational, vm)
    captured = _patch_backend(monkeypatch, operational, response=_fake_response(202))

    request = SimpleNamespace(
        user=SimpleNamespace(username="ops"),
        POST={},
    )
    view = getattr(operational, view_attr)()
    response = view.post(request, pk=vm.pk)

    assert captured["url"].endswith(f"/proxmox/qemu/100/{verb}")
    assert captured["params"] == {"endpoint_id": 7}
    assert captured["headers"]["X-Proxbox-API-Key"] == "secret"
    assert "Idempotency-Key" in captured["headers"]
    assert captured["verify"] is False
    assert response.url == "/virtualization/virtual-machines/42/"


def test_verb_post_skips_backend_when_unresolvable(monkeypatch):
    operational = _load(monkeypatch)
    vm = _make_vm()
    vm.custom_field_data = {}
    _bind_vm(monkeypatch, operational, vm)

    posts: list[object] = []
    monkeypatch.setattr(
        operational.requests,
        "post",
        lambda *a, **kw: posts.append((a, kw)),
    )
    monkeypatch.setattr(
        operational,
        "get_fastapi_request_context",
        lambda endpoint_id=None: SimpleNamespace(
            http_url="https://backend.example.com:8800",
            headers={},
            verify_ssl=True,
        ),
    )

    request = SimpleNamespace(user=SimpleNamespace(username="ops"), POST={})
    response = operational.OperationalStartView().post(request, pk=vm.pk)

    assert posts == []
    assert response.url == "/virtualization/virtual-machines/42/"


def test_verb_post_surfaces_backend_403_reason(monkeypatch):
    operational = _load(monkeypatch)
    vm = _make_vm()
    _bind_vm(monkeypatch, operational, vm)
    _patch_backend(
        monkeypatch,
        operational,
        response=_fake_response(403, {"reason": "endpoint_writes_disabled"}),
    )

    msgs = operational._messages_stub
    msgs.calls = []

    request = SimpleNamespace(user=SimpleNamespace(username="ops"), POST={})
    operational.OperationalStartView().post(request, pk=vm.pk)

    errors = [m for level, m in msgs.calls if level == "error"]
    flat = " ".join(str(m) for m in errors)
    assert "403" in flat
    assert "endpoint_writes_disabled" in flat


# ---------- Migrate-specific behaviour ----------


def test_migrate_post_requires_target(monkeypatch):
    operational = _load(monkeypatch)
    vm = _make_vm()
    _bind_vm(monkeypatch, operational, vm)

    posts: list[object] = []
    monkeypatch.setattr(
        operational.requests, "post", lambda *a, **kw: posts.append((a, kw))
    )

    request = SimpleNamespace(user=SimpleNamespace(username="ops"), POST={})
    response = operational.OperationalMigrateView().post(request, pk=vm.pk)

    assert posts == []
    assert response.url.endswith("proxbox-operational-migrate/")


def test_migrate_post_forwards_target_and_online(monkeypatch):
    operational = _load(monkeypatch)
    vm = _make_vm()
    _bind_vm(monkeypatch, operational, vm)
    captured = _patch_backend(monkeypatch, operational, response=_fake_response(202))

    request = SimpleNamespace(
        user=SimpleNamespace(username="ops"),
        POST={"target": "node-2", "online": "on"},
    )
    operational.OperationalMigrateView().post(request, pk=vm.pk)

    assert captured["url"].endswith("/proxmox/qemu/100/migrate")
    assert captured["json"] == {"target": "node-2", "online": True}
    assert captured["params"] == {"endpoint_id": 7}


def test_migrate_get_renders_picker_with_targets(monkeypatch):
    operational = _load(monkeypatch)
    vm = _make_vm()
    _bind_vm(monkeypatch, operational, vm)

    # Stub the ProxmoxNode queryset chain — `.filter().exclude().order_by()`.
    class _NodesQS:
        def __init__(self, items):
            self._items = items

        def filter(self, **kwargs):
            return self

        def exclude(self, **kwargs):
            self._items = [n for n in self._items if n.name != kwargs.get("name")]
            return self

        def order_by(self, *args):
            return list(self._items)

    nodes = [
        SimpleNamespace(name="node-1", online=True),
        SimpleNamespace(name="node-2", online=False),
    ]
    operational.ProxmoxNode.objects = SimpleNamespace(
        filter=lambda **kwargs: _NodesQS(nodes)
    )

    request = SimpleNamespace(user=SimpleNamespace(username="ops"), POST={})
    rendered = operational.OperationalMigrateView().get(request, pk=vm.pk)

    # The render stub returns a dict with 'context'.
    assert rendered["template"].endswith("vm_migrate_picker.html")
    assert rendered["context"]["resolvable"] is True
    assert [n.name for n in rendered["context"]["targets"]] == ["node-1", "node-2"]
