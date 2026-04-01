"""Contract tests for ProxmoxCluster and ProxmoxNode API layer."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text()


# ---------------------------------------------------------------------------
# Serializer contracts
# ---------------------------------------------------------------------------


def test_cluster_serializer_file_exists():
    path = REPO_ROOT / "netbox_proxbox/api/serializers/cluster.py"
    assert path.exists()


def test_cluster_serializer_exports_both_classes():
    content = _read("netbox_proxbox/api/serializers/cluster.py")
    assert "class ProxmoxClusterSerializer" in content
    assert "class ProxmoxNodeSerializer" in content


def test_cluster_serializer_includes_nested_endpoint_field():
    content = _read("netbox_proxbox/api/serializers/cluster.py")
    assert "endpoint" in content


def test_cluster_serializer_includes_netbox_cluster_field():
    content = _read("netbox_proxbox/api/serializers/cluster.py")
    assert "netbox_cluster" in content


def test_cluster_serializer_includes_netbox_device_field():
    content = _read("netbox_proxbox/api/serializers/cluster.py")
    assert "netbox_device" in content


def test_serializers_init_exports_cluster_serializers():
    content = _read("netbox_proxbox/api/serializers/__init__.py")
    assert "ProxmoxClusterSerializer" in content
    assert "ProxmoxNodeSerializer" in content


# ---------------------------------------------------------------------------
# ViewSet contracts
# ---------------------------------------------------------------------------


def test_cluster_viewsets_defined_in_views():
    content = _read("netbox_proxbox/api/views.py")
    assert "ProxmoxClusterViewSet" in content
    assert "ProxmoxNodeViewSet" in content


def test_cluster_viewsets_registered_in_urls():
    content = _read("netbox_proxbox/api/urls.py")
    assert "clusters" in content
    assert "nodes" in content


# ---------------------------------------------------------------------------
# FilterSet contracts
# ---------------------------------------------------------------------------


def test_cluster_filtersets_defined():
    content = _read("netbox_proxbox/filtersets.py")
    assert "ProxmoxClusterFilterSet" in content
    assert "ProxmoxNodeFilterSet" in content


def test_cluster_filterset_filters_by_endpoint():
    content = _read("netbox_proxbox/filtersets.py")
    assert "endpoint" in content


def test_cluster_filterset_filters_nodes_by_online_status():
    content = _read("netbox_proxbox/filtersets.py")
    assert "online" in content


# ---------------------------------------------------------------------------
# Table contracts
# ---------------------------------------------------------------------------


def test_cluster_tables_file_exists():
    path = REPO_ROOT / "netbox_proxbox/tables/cluster.py"
    assert path.exists()


def test_cluster_tables_define_expected_classes():
    content = _read("netbox_proxbox/tables/cluster.py")
    assert "ProxmoxClusterTable" in content
    assert "ProxmoxNodeTable" in content


def test_cluster_node_table_renders_memory_in_gb():
    content = _read("netbox_proxbox/tables/cluster.py")
    assert "render_memory" in content or "GB" in content


def test_tables_init_exports_cluster_tables():
    content = _read("netbox_proxbox/tables/__init__.py")
    assert "ProxmoxClusterTable" in content or "cluster" in content


# ---------------------------------------------------------------------------
# Tab view contracts
# ---------------------------------------------------------------------------


def test_cluster_nodes_tab_view_file_exists():
    path = REPO_ROOT / "netbox_proxbox/views/cluster_nodes_tab.py"
    assert path.exists()


def test_cluster_nodes_tab_view_registered_on_endpoint():
    content = _read("netbox_proxbox/views/cluster_nodes_tab.py")
    assert "register_model_view" in content
    assert "ProxmoxEndpoint" in content
    assert "cluster-nodes" in content or "cluster_nodes" in content


def test_views_init_exports_tab_view():
    content = _read("netbox_proxbox/views/__init__.py")
    assert (
        "ProxmoxEndpointClusterNodesTabView" in content
        or "cluster_nodes_tab" in content
    )
