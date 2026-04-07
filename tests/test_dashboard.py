from __future__ import annotations

from types import SimpleNamespace

from tests.conftest import ResponseStub, load_plugin_module


class _NodeQuerySet(list):
    def restrict(self, *args, **kwargs):
        return self

    def filter(self, *args, **kwargs):
        if not kwargs:
            return self

        def matches(item):
            for lookup, expected in kwargs.items():
                parts = lookup.split("__")
                operator = "exact"
                if parts[-1] == "in":
                    operator = "in"
                    parts = parts[:-1]

                value = item
                for part in parts:
                    value = getattr(value, part, None)

                if operator == "in":
                    if value not in expected:
                        return False
                elif value != expected:
                    return False

            return True

        return _NodeQuerySet(item for item in self if matches(item))

    def select_related(self, *args, **kwargs):
        return self

    def order_by(self, *fields):
        if not fields:
            return _NodeQuerySet(self)
        field = fields[0]
        reverse = False
        if field.startswith("-"):
            reverse = True
            field = field[1:]
        return _NodeQuerySet(
            sorted(self, key=lambda item: getattr(item, field), reverse=reverse)
        )


def _dashboard_request():
    return SimpleNamespace(
        method="GET",
        user=SimpleNamespace(
            is_authenticated=True,
            has_perm=lambda *args, **kwargs: True,
            has_perms=lambda *args, **kwargs: True,
        ),
    )


def test_dashboard_nodes_summary_uses_all_persisted_nodes(
    monkeypatch,
    fastapi_endpoint,
    proxmox_endpoint,
):
    module = load_plugin_module(
        "netbox_proxbox.views.dashboard",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
        proxmox_endpoint=proxmox_endpoint,
    )
    monkeypatch.setattr(
        module,
        "sync_proxmox_endpoint_to_backend",
        lambda *args, **kwargs: (True, None, None),
    )
    monkeypatch.setattr(
        module.ProxmoxNode,
        "objects",
        _NodeQuerySet(
            [
                SimpleNamespace(
                    name="pve-02",
                    endpoint=proxmox_endpoint,
                    online=False,
                    cpu_usage=0.25,
                    max_cpu=8,
                    memory_usage=32 * 1024**3,
                    max_memory=64 * 1024**3,
                    support_level="community",
                ),
                SimpleNamespace(
                    name="pve-01",
                    endpoint=proxmox_endpoint,
                    online=True,
                    cpu_usage=0.5,
                    max_cpu=16,
                    memory_usage=48 * 1024**3,
                    max_memory=128 * 1024**3,
                    support_level="enterprise",
                ),
            ]
        ),
        raising=False,
    )

    def fake_get(url, timeout=None, params=None, headers=None, verify=None):
        if "/proxmox/cluster/status" in url:
            return ResponseStub(
                [
                    {
                        "type": "cluster",
                        "name": "pve-cluster",
                        "nodes": 2,
                        "quorate": 1,
                    },
                    {"type": "node", "name": "pve-01", "status": "online", "online": 1},
                    {"type": "node", "name": "pve-02", "status": "online", "online": 1},
                ]
            )
        if "/proxmox/cluster/resources" in url:
            return ResponseStub(
                [
                    {"type": "qemu", "status": "running"},
                    {"type": "lxc", "status": "stopped"},
                ]
            )
        if "/proxmox/nodes/" in url:
            return ResponseStub(
                [
                    {
                        "node": "pve-01",
                        "status": "online",
                        "uptime": 86400,
                        "cpu": 0.5,
                        "maxcpu": 16,
                        "loadavg": [0.1, 0.2, 0.3],
                        "mem": 48 * 1024**3,
                        "maxmem": 128 * 1024**3,
                        "disk": 120 * 1024**3,
                        "maxdisk": 256 * 1024**3,
                    }
                ]
            )
        raise AssertionError(url)

    monkeypatch.setattr(module.requests, "get", fake_get)

    response = module.DashboardView.as_view()(_dashboard_request())
    dashboard = response["context"]["dashboards"][0]

    assert [row["name"] for row in dashboard["nodes"]] == ["pve-01", "pve-02"]
    assert len(dashboard["nodes"]) == 2
    assert dashboard["nodes"][0]["status"] == "online"
    assert dashboard["nodes"][1]["status"] == "offline"
    assert dashboard["nodes"][0]["disk_label"] == "120.00 GiB / 256.00 GiB"
    assert dashboard["cluster_summary"]["nodes_total"] == 2
    assert dashboard["cluster_summary"]["nodes_online"] == 1
    assert dashboard["cluster_summary"]["nodes_offline"] == 1


def test_dashboard_nodes_summary_falls_back_to_live_payload_when_needed(
    monkeypatch,
    fastapi_endpoint,
    proxmox_endpoint,
):
    module = load_plugin_module(
        "netbox_proxbox.views.dashboard",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
        proxmox_endpoint=proxmox_endpoint,
    )
    monkeypatch.setattr(
        module,
        "sync_proxmox_endpoint_to_backend",
        lambda *args, **kwargs: (True, None, None),
    )
    monkeypatch.setattr(module.ProxmoxNode, "objects", _NodeQuerySet(), raising=False)

    def fake_get(url, timeout=None, params=None, headers=None, verify=None):
        if "/proxmox/cluster/status" in url:
            return ResponseStub(
                [
                    {
                        "type": "cluster",
                        "name": "pve-cluster",
                        "nodes": 2,
                        "quorate": 1,
                    },
                    {"type": "node", "name": "pve-01", "status": "online", "online": 1},
                    {"type": "node", "name": "pve-02", "status": "online", "online": 1},
                ]
            )
        if "/proxmox/cluster/resources" in url:
            return ResponseStub(
                [
                    {"type": "qemu", "status": "running"},
                    {"type": "lxc", "status": "stopped"},
                ]
            )
        if "/proxmox/nodes/" in url:
            return ResponseStub(
                [
                    {
                        "node": "pve-01",
                        "status": "online",
                        "uptime": 86400,
                        "cpu": 0.125,
                        "maxcpu": 16,
                        "loadavg": [0.1, 0.2, 0.3],
                        "mem": 48 * 1024**3,
                        "maxmem": 128 * 1024**3,
                        "disk": 120 * 1024**3,
                        "maxdisk": 256 * 1024**3,
                    },
                    {
                        "node": "pve-02",
                        "status": "offline",
                        "uptime": 0,
                        "cpu": 0.0,
                        "maxcpu": 8,
                        "loadavg": [0.0, 0.0, 0.0],
                        "mem": 32 * 1024**3,
                        "maxmem": 64 * 1024**3,
                        "disk": 80 * 1024**3,
                        "maxdisk": 128 * 1024**3,
                    },
                ]
            )
        raise AssertionError(url)

    monkeypatch.setattr(module.requests, "get", fake_get)

    response = module.DashboardView.as_view()(_dashboard_request())
    dashboard = response["context"]["dashboards"][0]

    assert len(dashboard["nodes"]) == 2
    assert dashboard["nodes"][0]["name"] == "pve-01"
    assert dashboard["nodes"][1]["name"] == "pve-02"
    assert dashboard["nodes"][0]["loadavg"] == "0.10, 0.20, 0.30"
    assert dashboard["nodes"][1]["disk_label"] == "80.00 GiB / 128.00 GiB"
    assert dashboard["cluster_summary"]["nodes_total"] == 2
    assert dashboard["cluster_summary"]["nodes_online"] == 1
    assert dashboard["cluster_summary"]["nodes_offline"] == 1


def test_dashboard_nodes_summary_includes_live_nodes_missing_from_database(
    monkeypatch,
    fastapi_endpoint,
    proxmox_endpoint,
):
    module = load_plugin_module(
        "netbox_proxbox.views.dashboard",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
        proxmox_endpoint=proxmox_endpoint,
    )
    monkeypatch.setattr(
        module,
        "sync_proxmox_endpoint_to_backend",
        lambda *args, **kwargs: (True, None, None),
    )
    monkeypatch.setattr(
        module.ProxmoxNode,
        "objects",
        _NodeQuerySet(
            [
                SimpleNamespace(
                    name="pve-01",
                    endpoint=proxmox_endpoint,
                    online=True,
                    cpu_usage=0.5,
                    max_cpu=16,
                    memory_usage=48 * 1024**3,
                    max_memory=128 * 1024**3,
                    support_level="enterprise",
                )
            ]
        ),
        raising=False,
    )

    def fake_get(url, timeout=None, params=None, headers=None, verify=None):
        if "/proxmox/cluster/status" in url:
            return ResponseStub(
                [
                    {
                        "type": "cluster",
                        "name": "pve-cluster",
                        "nodes": 2,
                        "quorate": 1,
                    },
                    {"type": "node", "name": "pve-01", "status": "online", "online": 1},
                    {
                        "type": "node",
                        "name": "pve-02",
                        "status": "offline",
                        "online": 0,
                    },
                ]
            )
        if "/proxmox/cluster/resources" in url:
            return ResponseStub(
                [
                    {"type": "qemu", "status": "running"},
                    {"type": "lxc", "status": "stopped"},
                ]
            )
        if "/proxmox/nodes/" in url:
            return ResponseStub(
                [
                    {
                        "node": "pve-01",
                        "status": "online",
                        "uptime": 86400,
                        "cpu": 0.125,
                        "maxcpu": 16,
                        "loadavg": [0.1, 0.2, 0.3],
                        "mem": 48 * 1024**3,
                        "maxmem": 128 * 1024**3,
                        "disk": 120 * 1024**3,
                        "maxdisk": 256 * 1024**3,
                    },
                    {
                        "node": "pve-02",
                        "status": "offline",
                        "uptime": 0,
                        "cpu": 0.0,
                        "maxcpu": 8,
                        "loadavg": [0.0, 0.0, 0.0],
                        "mem": 32 * 1024**3,
                        "maxmem": 64 * 1024**3,
                        "disk": 80 * 1024**3,
                        "maxdisk": 128 * 1024**3,
                    },
                ]
            )
        raise AssertionError(url)

    monkeypatch.setattr(module.requests, "get", fake_get)

    response = module.DashboardView.as_view()(_dashboard_request())
    dashboard = response["context"]["dashboards"][0]

    assert [row["name"] for row in dashboard["nodes"]] == ["pve-01", "pve-02"]
    assert dashboard["nodes"][1]["disk_label"] == "80.00 GiB / 128.00 GiB"
    assert dashboard["cluster_summary"]["nodes_total"] == 2
    assert dashboard["cluster_summary"]["nodes_online"] == 1
    assert dashboard["cluster_summary"]["nodes_offline"] == 1


def test_dashboard_nodes_summary_includes_cluster_sibling_nodes_from_database(
    monkeypatch,
    fastapi_endpoint,
    proxmox_endpoint,
):
    module = load_plugin_module(
        "netbox_proxbox.views.dashboard",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
        proxmox_endpoint=proxmox_endpoint,
    )
    monkeypatch.setattr(
        module,
        "sync_proxmox_endpoint_to_backend",
        lambda *args, **kwargs: (True, None, None),
    )

    cluster = SimpleNamespace(name="pve-cluster")
    sibling_endpoint = SimpleNamespace(name="pve-02-endpoint")
    monkeypatch.setattr(
        module.ProxmoxNode,
        "objects",
        _NodeQuerySet(
            [
                SimpleNamespace(
                    name="pve-01",
                    endpoint=proxmox_endpoint,
                    proxmox_cluster=cluster,
                    online=True,
                    cpu_usage=0.5,
                    max_cpu=16,
                    memory_usage=48 * 1024**3,
                    max_memory=128 * 1024**3,
                    support_level="enterprise",
                ),
                SimpleNamespace(
                    name="pve-02",
                    endpoint=sibling_endpoint,
                    proxmox_cluster=cluster,
                    online=False,
                    cpu_usage=0.25,
                    max_cpu=8,
                    memory_usage=32 * 1024**3,
                    max_memory=64 * 1024**3,
                    support_level="community",
                ),
            ]
        ),
        raising=False,
    )

    def fake_get(url, timeout=None, params=None, headers=None, verify=None):
        if "/proxmox/cluster/status" in url:
            return ResponseStub(
                [
                    {
                        "type": "cluster",
                        "name": "pve-cluster",
                        "nodes": 2,
                        "quorate": 1,
                    },
                    {"type": "node", "name": "pve-01", "status": "online", "online": 1},
                    {
                        "type": "node",
                        "name": "pve-02",
                        "status": "offline",
                        "online": 0,
                    },
                ]
            )
        if "/proxmox/cluster/resources" in url:
            return ResponseStub(
                [
                    {"type": "qemu", "status": "running"},
                    {"type": "lxc", "status": "stopped"},
                ]
            )
        if "/proxmox/nodes/" in url:
            return ResponseStub(
                [
                    {
                        "node": "pve-01",
                        "status": "online",
                        "uptime": 86400,
                        "cpu": 0.125,
                        "maxcpu": 16,
                        "loadavg": [0.1, 0.2, 0.3],
                        "mem": 48 * 1024**3,
                        "maxmem": 128 * 1024**3,
                        "disk": 120 * 1024**3,
                        "maxdisk": 256 * 1024**3,
                    }
                ]
            )
        raise AssertionError(url)

    monkeypatch.setattr(module.requests, "get", fake_get)

    response = module.DashboardView.as_view()(_dashboard_request())
    dashboard = response["context"]["dashboards"][0]

    assert [row["name"] for row in dashboard["nodes"]] == ["pve-01", "pve-02"]
    assert dashboard["nodes"][0]["disk_label"] == "120.00 GiB / 256.00 GiB"
    assert dashboard["nodes"][1]["status"] == "offline"
    assert dashboard["cluster_summary"]["nodes_total"] == 2
    assert dashboard["cluster_summary"]["nodes_online"] == 1
    assert dashboard["cluster_summary"]["nodes_offline"] == 1
