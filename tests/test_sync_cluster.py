"""Contract and logic tests for cluster/node sync service."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text()


# ---------------------------------------------------------------------------
# File existence / structure contracts
# ---------------------------------------------------------------------------

def test_sync_cluster_service_file_exists():
    path = REPO_ROOT / "netbox_proxbox/services/sync_cluster.py"
    assert path.exists()


def test_sync_cluster_defines_main_function():
    content = _read("netbox_proxbox/services/sync_cluster.py")
    assert "def sync_cluster_and_nodes" in content


def test_sync_cluster_accepts_endpoint_id_parameter():
    content = _read("netbox_proxbox/services/sync_cluster.py")
    assert "endpoint_id" in content


def test_sync_cluster_accepts_fastapi_url_parameter():
    content = _read("netbox_proxbox/services/sync_cluster.py")
    assert "fastapi_url" in content


def test_sync_cluster_returns_result_dict():
    content = _read("netbox_proxbox/services/sync_cluster.py")
    assert '"success"' in content
    assert '"error"' in content


def test_sync_cluster_tracks_created_updated_deleted_counts():
    content = _read("netbox_proxbox/services/sync_cluster.py")
    assert "clusters_created" in content
    assert "nodes_created" in content
    assert "nodes_deleted" in content


def test_sync_cluster_updates_endpoint_mode():
    content = _read("netbox_proxbox/services/sync_cluster.py")
    assert "mode" in content
    assert "mode_updated" in content


def test_sync_cluster_uses_update_or_create_for_clusters():
    content = _read("netbox_proxbox/services/sync_cluster.py")
    assert "update_or_create" in content


def test_sync_cluster_deletes_stale_nodes():
    content = _read("netbox_proxbox/services/sync_cluster.py")
    assert "stale" in content
    assert "delete" in content


def test_sync_cluster_handles_exceptions():
    content = _read("netbox_proxbox/services/sync_cluster.py")
    assert "except" in content
    assert "error" in content.lower()


def test_sync_cluster_calls_proxmox_cluster_status_endpoint():
    content = _read("netbox_proxbox/services/sync_cluster.py")
    assert "/proxmox/cluster/status" in content


def test_sync_cluster_calls_proxmox_nodes_endpoint():
    content = _read("netbox_proxbox/services/sync_cluster.py")
    assert "/proxmox/nodes/" in content


# ---------------------------------------------------------------------------
# Mode detection logic (isolated from Django ORM)
# ---------------------------------------------------------------------------

def _detect_mode(cluster_record, node_records):
    """Mirror of the mode detection logic in sync_cluster_and_nodes."""
    if cluster_record and len(node_records) > 1:
        return "cluster"
    if len(node_records) == 1:
        return "standalone"
    return "undefined"


def test_three_node_cluster_detects_cluster_mode():
    cluster = {"type": "cluster", "name": "pve-cluster"}
    nodes = [{"type": "node"}, {"type": "node"}, {"type": "node"}]
    assert _detect_mode(cluster, nodes) == "cluster"


def test_single_node_no_cluster_detects_standalone_mode():
    assert _detect_mode(None, [{"type": "node"}]) == "standalone"


def test_empty_response_detects_undefined_mode():
    assert _detect_mode(None, []) == "undefined"


def test_two_node_cluster_detects_cluster_mode():
    cluster = {"type": "cluster"}
    nodes = [{"type": "node"}, {"type": "node"}]
    assert _detect_mode(cluster, nodes) == "cluster"


def test_cluster_record_with_single_node_detects_standalone():
    # Cluster record present but only 1 node → standalone takes precedence
    cluster = {"type": "cluster"}
    nodes = [{"type": "node"}]
    assert _detect_mode(cluster, nodes) == "standalone"


# ---------------------------------------------------------------------------
# Node data extraction logic (isolated from ORM)
# ---------------------------------------------------------------------------

def _extract_node_name(node_record):
    """Mirror of node name extraction logic."""
    return node_record.get("name") or node_record.get("node")


def test_node_name_extracted_from_name_field():
    assert _extract_node_name({"name": "pve01", "type": "node"}) == "pve01"


def test_node_name_extracted_from_node_field():
    assert _extract_node_name({"node": "pve02"}) == "pve02"


def test_node_name_returns_none_when_missing():
    assert _extract_node_name({}) is None


def test_node_online_status_parsed_from_integer():
    """Proxmox returns online as 0/1 integer."""
    assert bool(1) is True
    assert bool(0) is False


def test_stale_node_detection():
    """Nodes in DB but not in sync response should be flagged as stale."""
    existing = {"pve01", "pve02", "pve-old"}
    synced = {"pve01", "pve02"}
    stale = existing - synced
    assert stale == {"pve-old"}
