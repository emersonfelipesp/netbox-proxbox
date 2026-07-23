"""Behavior tests for ``services.sync_datacenter.sync_datacenter`` scoping.

Loaded by file path against stubbed ``django``, ``netbox_proxbox.models``,
``backend_proxy`` and ``endpoint_scope`` modules — no NetBox bootstrap and no
HTTP. Pins the half of the endpoint scope that query-param forwarding cannot
give: a response row for an endpoint outside the run's selection must be
refused locally, because a backend that ignores ``proxmox_endpoint_ids`` (an
older release, or a bug) returns every endpoint's clusters anyway, and the
by-cluster-name resolution would otherwise upsert CPU models — and mark rows
stale — for endpoints the caller explicitly excluded.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def sync_dc_module(monkeypatch):
    """Load sync_datacenter.py with all Django/plugin dependencies stubbed."""
    pkg = types.ModuleType("netbox_proxbox")
    pkg.__path__ = [str(REPO_ROOT / "netbox_proxbox")]
    monkeypatch.setitem(sys.modules, "netbox_proxbox", pkg)

    choices = types.ModuleType("netbox_proxbox.choices")
    choices.FirewallSyncStatusChoices = SimpleNamespace(ACTIVE="active", STALE="stale")
    monkeypatch.setitem(sys.modules, "netbox_proxbox.choices", choices)

    cpu_mgr = SimpleNamespace(upserts=[], stale_calls=[])

    class _CpuManager:
        def get_or_create(self, defaults=None, **lookup):
            cpu_mgr.upserts.append(lookup)
            return SimpleNamespace(pk=len(cpu_mgr.upserts)), True

        def filter(self, **kwargs):
            cpu_mgr.stale_calls.append(kwargs)
            return self

        def exclude(self, **_kw):
            return self

        def update(self, **_kw):
            return 0

    class _ProxmoxDatacenterCpuModel:
        objects = _CpuManager()

    class _ProxmoxEndpoint:
        class objects:
            @staticmethod
            def filter(**_kw):
                return SimpleNamespace(first=lambda: None)

    models = types.ModuleType("netbox_proxbox.models")
    models.ProxmoxDatacenterCpuModel = _ProxmoxDatacenterCpuModel
    models.ProxmoxEndpoint = _ProxmoxEndpoint
    monkeypatch.setitem(sys.modules, "netbox_proxbox.models", models)

    services_pkg = types.ModuleType("netbox_proxbox.services")
    services_pkg.__path__ = [str(REPO_ROOT / "netbox_proxbox" / "services")]
    monkeypatch.setitem(sys.modules, "netbox_proxbox.services", services_pkg)
    backend_proxy = types.ModuleType("netbox_proxbox.services.backend_proxy")
    backend_proxy.get_fastapi_request_context = lambda endpoint_id=None: None
    monkeypatch.setitem(
        sys.modules, "netbox_proxbox.services.backend_proxy", backend_proxy
    )
    endpoint_scope = types.ModuleType("netbox_proxbox.services.endpoint_scope")
    endpoint_scope.enabled_backend_endpoint_scope = lambda **_kw: (
        {"source": "database", "proxmox_endpoint_ids": "11"},
        {1: 11},
        None,
    )
    monkeypatch.setitem(
        sys.modules, "netbox_proxbox.services.endpoint_scope", endpoint_scope
    )

    django_pkg = types.ModuleType("django")
    monkeypatch.setitem(sys.modules, "django", django_pkg)
    db_mod = types.ModuleType("django.db")

    class _Atomic:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    db_mod.transaction = SimpleNamespace(atomic=lambda: _Atomic())
    monkeypatch.setitem(sys.modules, "django.db", db_mod)

    sys.modules.pop("netbox_proxbox.services.sync_datacenter", None)
    spec = importlib.util.spec_from_file_location(
        "netbox_proxbox.services.sync_datacenter",
        REPO_ROOT / "netbox_proxbox" / "services" / "sync_datacenter.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "netbox_proxbox.services.sync_datacenter", module)
    spec.loader.exec_module(module)
    module._cpu_mgr = cpu_mgr
    return module


def test_out_of_scope_cpu_models_are_refused(sync_dc_module, monkeypatch):
    """A CPU-model row for an endpoint outside the run's scope is never written.

    The stubbed scope resolves only endpoint pk 1, while the backend response
    carries a second cluster owned by endpoint pk 2 — the shape an older
    proxbox-api ignoring ``proxmox_endpoint_ids`` produces. Only endpoint 1's
    model may be upserted, and stale marking may only touch endpoint 1's rows.
    """
    in_scope = SimpleNamespace(pk=1)
    out_of_scope = SimpleNamespace(pk=2)
    monkeypatch.setattr(
        sync_dc_module,
        "_resolve_endpoint_by_cluster_name",
        lambda name: {"cluster-in": in_scope, "cluster-out": out_of_scope}.get(name),
    )

    payload = [
        {"cluster_name": "cluster-in", "cputype": "x86-64-v3"},
        {"cluster_name": "cluster-out", "cputype": "x86-64-v4"},
    ]
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = payload

    with patch.object(sync_dc_module.requests, "get", return_value=mock_resp):
        result = sync_dc_module.sync_datacenter(
            fastapi_url="http://backend:8000", endpoint_ids=[1]
        )

    assert result.success is True
    assert result.cpu_models_created == 1
    assert result.endpoints_processed == 1
    assert [row["endpoint_id"] for row in result.per_endpoint] == [1]
    assert [u["endpoint"].pk for u in sync_dc_module._cpu_mgr.upserts] == [1], (
        "the out-of-scope endpoint's CPU model must be refused, not upserted"
    )
    assert sync_dc_module._cpu_mgr.stale_calls == [{"endpoint_id__in": {1}}], (
        "stale marking must stay inside the run's scope"
    )


def test_a_cluster_name_claimed_by_two_endpoints_is_refused(
    sync_dc_module, monkeypatch
):
    """Ambiguous cluster names must resolve to nobody — same rule as firewall.

    A refused resolution feeds the existing skip branch, so the ambiguous row
    is neither upserted under the wrong endpoint nor allowed to impersonate an
    in-scope one through the shared name.
    """
    rows = [
        SimpleNamespace(endpoint=SimpleNamespace(pk=1), endpoint_id=1),
        SimpleNamespace(endpoint=SimpleNamespace(pk=2), endpoint_id=2),
    ]

    class _AmbiguousCluster:
        class objects:
            @staticmethod
            def filter(**_kw):
                class _qs:
                    @staticmethod
                    def select_related(*_a):
                        return rows

                return _qs()

    models = sys.modules["netbox_proxbox.models"]
    monkeypatch.setattr(models, "ProxmoxCluster", _AmbiguousCluster, raising=False)

    assert sync_dc_module._resolve_endpoint_by_cluster_name("pve") is None
