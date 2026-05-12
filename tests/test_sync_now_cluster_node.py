"""Tests for sync_now cluster and node views."""

from __future__ import annotations

import sys
import types
from types import SimpleNamespace

from tests.conftest import load_plugin_module


def _add_sync_now_stubs(monkeypatch, individual_sync_response=None):
    """Add stubs for individual_sync and sync_now package needed by cluster/node views."""
    individual_sync_mod = types.ModuleType("netbox_proxbox.services.individual_sync")
    captured: dict = {}

    if individual_sync_response is None:
        individual_sync_response = ({"action": "synced"}, 200, [])

    def fake_sync(endpoint, params, **kwargs):
        captured["endpoint"] = endpoint
        captured["params"] = params
        captured["kwargs"] = kwargs
        return individual_sync_response

    individual_sync_mod.sync_individual_with_dependencies = fake_sync
    monkeypatch.setitem(
        sys.modules,
        "netbox_proxbox.services.individual_sync",
        individual_sync_mod,
    )

    branch_lifecycle_mod = types.ModuleType("netbox_proxbox.services.branch_lifecycle")
    branch_lifecycle_mod.get_active_branch_schema_id = lambda: None
    monkeypatch.setitem(
        sys.modules,
        "netbox_proxbox.services.branch_lifecycle",
        branch_lifecycle_mod,
    )

    sync_now_pkg = types.ModuleType("netbox_proxbox.views.sync_now")
    sync_now_pkg.__path__ = []

    def _handle_sync_response(request, response, status, dependencies, label, url):
        from tests.conftest import HttpResponseRedirect

        return HttpResponseRedirect(url)

    sync_now_pkg._handle_sync_response = _handle_sync_response
    monkeypatch.setitem(sys.modules, "netbox_proxbox.views.sync_now", sync_now_pkg)

    return captured


def test_cluster_sync_now_redirects_to_cluster_url(monkeypatch):
    captured = _add_sync_now_stubs(monkeypatch)

    cluster_view = load_plugin_module(
        "netbox_proxbox.views.sync_now.cluster",
        monkeypatch=monkeypatch,
    )

    cluster = SimpleNamespace(
        pk=7,
        name="pve-cluster",
        get_absolute_url=lambda: "/plugins/proxbox/clusters/7/",
    )
    monkeypatch.setattr(
        cluster_view,
        "get_object_or_404",
        lambda *args, **kwargs: cluster,
    )

    request = SimpleNamespace(user=SimpleNamespace(username="admin"))
    response = cluster_view.ProxmoxClusterSyncNowView().post(request, pk=7)

    assert response.url == "/plugins/proxbox/clusters/7/"
    assert captured["endpoint"] == "sync/individual/cluster"
    assert captured["params"]["cluster_name"] == "pve-cluster"


def test_cluster_sync_now_passes_error_status(monkeypatch):
    _add_sync_now_stubs(
        monkeypatch, individual_sync_response=({"error": "backend down"}, 503, [])
    )

    cluster_view = load_plugin_module(
        "netbox_proxbox.views.sync_now.cluster",
        monkeypatch=monkeypatch,
    )

    cluster = SimpleNamespace(
        pk=3,
        name="pve-cluster",
        get_absolute_url=lambda: "/plugins/proxbox/clusters/3/",
    )
    monkeypatch.setattr(
        cluster_view, "get_object_or_404", lambda *args, **kwargs: cluster
    )

    request = SimpleNamespace(user=SimpleNamespace(username="admin"))
    response = cluster_view.ProxmoxClusterSyncNowView().post(request, pk=3)

    assert response.url == "/plugins/proxbox/clusters/3/"


def test_node_sync_now_redirects_to_node_url(monkeypatch):
    captured = _add_sync_now_stubs(monkeypatch)

    node_view = load_plugin_module(
        "netbox_proxbox.views.sync_now.node",
        monkeypatch=monkeypatch,
    )

    node = SimpleNamespace(
        pk=12,
        name="pve-node1",
        proxmox_cluster=SimpleNamespace(name="pve-cluster"),
        netbox_device=None,
        get_absolute_url=lambda: "/plugins/proxbox/nodes/12/",
    )
    monkeypatch.setattr(node_view, "get_object_or_404", lambda *args, **kwargs: node)

    request = SimpleNamespace(user=SimpleNamespace(username="admin"))
    response = node_view.ProxmoxNodeSyncNowView().post(request, pk=12)

    assert response.url == "/plugins/proxbox/nodes/12/"
    assert captured["endpoint"] == "sync/individual/node"
    assert captured["params"]["node_name"] == "pve-node1"
    assert captured["params"]["cluster_name"] == "pve-cluster"


def test_node_sync_now_no_cluster_redirects_with_error(monkeypatch):
    _add_sync_now_stubs(monkeypatch)

    node_view = load_plugin_module(
        "netbox_proxbox.views.sync_now.node",
        monkeypatch=monkeypatch,
    )

    node = SimpleNamespace(
        pk=99,
        name="orphan-node",
        proxmox_cluster=None,
        netbox_device=None,
        get_absolute_url=lambda: "/plugins/proxbox/nodes/99/",
    )
    monkeypatch.setattr(node_view, "get_object_or_404", lambda *args, **kwargs: node)

    request = SimpleNamespace(user=SimpleNamespace(username="admin"))
    response = node_view.ProxmoxNodeSyncNowView().post(request, pk=99)

    assert response.url == "/plugins/proxbox/nodes/99/"
