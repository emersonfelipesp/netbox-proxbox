"""Tests for test_dashboard."""

from __future__ import annotations

from types import SimpleNamespace

from tests.conftest import ResponseStub, _make_model_class, load_plugin_module


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


def test_dashboard_includes_cluster_siblings_via_proxmox_cluster_endpoint(
    monkeypatch,
    fastapi_endpoint,
    proxmox_endpoint,
):
    """Nodes linked to clusters owned by this endpoint are included even when
    the node's own endpoint FK points elsewhere."""
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

    # pve-01 is directly linked to the endpoint; pve-02 has its proxmox_cluster
    # owned by the same endpoint but its own endpoint FK is a sibling endpoint.
    cluster = SimpleNamespace(name="pve-cluster", endpoint=proxmox_endpoint)
    sibling_endpoint = SimpleNamespace(name="pve-02-direct-endpoint")
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
                    cpu_usage=0.1,
                    max_cpu=8,
                    memory_usage=16 * 1024**3,
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
            return ResponseStub([{"type": "qemu", "status": "running"}])
        if "/proxmox/nodes/" in url:
            return ResponseStub(
                [
                    {
                        "node": "pve-01",
                        "status": "online",
                        "uptime": 3600,
                        "cpu": 0.5,
                        "maxcpu": 16,
                        "loadavg": [0.2, 0.3, 0.4],
                        "mem": 48 * 1024**3,
                        "maxmem": 128 * 1024**3,
                        "disk": 50 * 1024**3,
                        "maxdisk": 100 * 1024**3,
                    }
                ]
            )
        raise AssertionError(url)

    monkeypatch.setattr(module.requests, "get", fake_get)

    response = module.DashboardView.as_view()(_dashboard_request())
    dashboard = response["context"]["dashboards"][0]

    assert [row["name"] for row in dashboard["nodes"]] == ["pve-01", "pve-02"]
    assert dashboard["nodes"][1]["status"] == "offline"
    assert dashboard["cluster_summary"]["nodes_total"] == 2


def test_dashboard_object_summaries_present_in_context(
    monkeypatch,
    fastapi_endpoint,
    proxmox_endpoint,
):
    """Dashboard context always includes object_summaries list."""
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
                        "nodes": 1,
                        "quorate": 1,
                    },
                    {"type": "node", "name": "pve-01", "status": "online", "online": 1},
                ]
            )
        if "/proxmox/cluster/resources" in url:
            return ResponseStub([])
        if "/proxmox/nodes/" in url:
            return ResponseStub(
                [
                    {
                        "node": "pve-01",
                        "status": "online",
                        "uptime": 1000,
                        "cpu": 0.1,
                        "maxcpu": 4,
                        "loadavg": [0.0, 0.0, 0.0],
                        "mem": 1 * 1024**3,
                        "maxmem": 8 * 1024**3,
                        "disk": 10 * 1024**3,
                        "maxdisk": 50 * 1024**3,
                    }
                ]
            )
        raise AssertionError(url)

    monkeypatch.setattr(module.requests, "get", fake_get)

    response = module.DashboardView.as_view()(_dashboard_request())
    dashboard = response["context"]["dashboards"][0]

    assert "object_summaries" in dashboard
    assert isinstance(dashboard["object_summaries"], list)
    # Without a linked NetBox cluster only endpoint-scoped objects are shown
    labels = [obj["label"] for obj in dashboard["object_summaries"]]
    assert "Backup Routines" in labels
    assert "Replications" in labels


def test_build_object_summaries_counts(monkeypatch, proxmox_endpoint):
    """build_object_summaries returns correct counts from model querysets."""
    import sys
    import types
    from tests.conftest import load_plugin_module

    module = load_plugin_module(
        "netbox_proxbox.views.dashboard_data",
        monkeypatch=monkeypatch,
        proxmox_endpoint=proxmox_endpoint,
    )

    # Build a minimal queryset stub that returns preset counts per filter key
    class _CountingQS:
        def __init__(self, total=0, counts_by_kwarg=None):
            self._total = total
            self._counts_by_kwarg = counts_by_kwarg or {}

        def filter(self, **kwargs):
            # Match on single-key hashable values (e.g. enabled=True, status="active").
            # Non-hashable values (e.g. model objects) are skipped; the same QS is
            # returned so chained filters like .filter(endpoint=...).filter(enabled=True)
            # still resolve correctly.
            for k, v in kwargs.items():
                try:
                    if (k, v) in self._counts_by_kwarg:
                        return _CountingQS(total=self._counts_by_kwarg[(k, v)])
                except TypeError:
                    pass
            # No match — preserve counts_by_kwarg so chained filters still work
            return _CountingQS(total=self._total, counts_by_kwarg=self._counts_by_kwarg)

        def count(self):
            return self._total

    class _ModelWithQS:
        def __init__(self, qs):
            self.objects = qs

    module.BackupRoutine = _ModelWithQS(
        _CountingQS(
            total=5,
            counts_by_kwarg={("enabled", True): 3},
        )
    )
    module.Replication = _ModelWithQS(
        _CountingQS(
            total=4,
            counts_by_kwarg={("status", "active"): 3, ("status", "stale"): 1},
        )
    )
    module.ProxmoxStorage = _ModelWithQS(_CountingQS(total=0))
    module.VMBackup = _ModelWithQS(_CountingQS(total=0))
    module.VMSnapshot = _ModelWithQS(_CountingQS(total=0))
    module.ProxmoxStorageVirtualDisk = _ModelWithQS(_CountingQS(total=0))

    summaries = module.build_object_summaries(proxmox_endpoint, netbox_cluster=None)

    labels = {s["label"]: s for s in summaries}
    assert labels["Backup Routines"]["total"] == 5
    assert "3 enabled" in labels["Backup Routines"]["detail"]
    assert "2 disabled" in labels["Backup Routines"]["detail"]
    assert labels["Replications"]["total"] == 4
    assert "3 active" in labels["Replications"]["detail"]
    assert "1 stale" in labels["Replications"]["detail"]
    # Storage/backup/snapshot/disk cards absent when netbox_cluster is None
    assert "Storage" not in labels
    assert "VM Backups" not in labels
