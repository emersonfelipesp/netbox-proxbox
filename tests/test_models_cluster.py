"""Contract and logic tests for ProxmoxCluster and ProxmoxNode models."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace


REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text()


# ---------------------------------------------------------------------------
# Memory / CPU property logic tests
# These verify the calculation formulas without needing a real Django ORM.
# ---------------------------------------------------------------------------


def _memory_usage_percent(memory_usage, max_memory):
    """Mirror of ProxmoxNode.memory_usage_percent property."""
    if not memory_usage or not max_memory:
        return None
    return round(memory_usage / max_memory * 100, 1)


def _cpu_usage_percent(cpu_usage):
    """Mirror of ProxmoxNode.cpu_usage_percent property."""
    return cpu_usage


def test_memory_usage_percent_calculation():
    """8 GB used / 16 GB total = 50.0 %."""
    mem_used = 8_589_934_592  # 8 GiB
    mem_total = 17_179_869_184  # 16 GiB
    assert _memory_usage_percent(mem_used, mem_total) == 50.0


def test_memory_usage_percent_with_partial_data():
    """Calculation with varied ratios rounds correctly."""
    # 12 GB / 16 GB = 75 %
    assert _memory_usage_percent(12_884_901_888, 17_179_869_184) == 75.0
    # 1 GB / 8 GB = 12.5 %
    assert _memory_usage_percent(1_073_741_824, 8_589_934_592) == 12.5


def test_memory_usage_percent_returns_none_when_no_data():
    assert _memory_usage_percent(None, None) is None
    assert _memory_usage_percent(0, 0) is None
    assert _memory_usage_percent(0, 17_179_869_184) is None


def test_cpu_usage_percent_passes_through():
    assert _cpu_usage_percent(75.5) == 75.5
    assert _cpu_usage_percent(0.0) == 0.0
    assert _cpu_usage_percent(100.0) == 100.0


# ---------------------------------------------------------------------------
# Mode detection logic tests (mirrors sync_cluster.py mode detection)
# ---------------------------------------------------------------------------


def _detect_mode(cluster_record, node_records):
    """Mirror of mode detection logic in sync_cluster.sync_cluster_and_nodes."""
    if cluster_record and len(node_records) > 1:
        return "cluster"
    if len(node_records) == 1:
        return "standalone"
    return "undefined"


def test_mode_detection_cluster():
    cluster = {"type": "cluster", "name": "pve"}
    nodes = [{"type": "node"}, {"type": "node"}, {"type": "node"}]
    assert _detect_mode(cluster, nodes) == "cluster"


def test_mode_detection_standalone():
    nodes = [{"type": "node"}]
    assert _detect_mode(None, nodes) == "standalone"


def test_mode_detection_undefined_when_no_nodes():
    assert _detect_mode(None, []) == "undefined"


def test_mode_detection_cluster_with_two_nodes():
    cluster = {"type": "cluster"}
    nodes = [{"type": "node"}, {"type": "node"}]
    assert _detect_mode(cluster, nodes) == "cluster"


# ---------------------------------------------------------------------------
# File / template existence contracts
# ---------------------------------------------------------------------------


def test_proxmox_cluster_model_file_exists():
    path = REPO_ROOT / "netbox_proxbox/models/proxmox_cluster.py"
    assert path.exists()


def test_proxmox_node_model_file_exists():
    path = REPO_ROOT / "netbox_proxbox/models/proxmox_node.py"
    assert path.exists()


def test_proxmox_cluster_model_defines_expected_fields():
    content = _read("netbox_proxbox/models/proxmox_cluster.py")
    assert "class ProxmoxCluster" in content
    assert "netbox_cluster" in content
    assert "quorate" in content
    assert "nodes_count" in content
    assert "mode" in content


def test_proxmox_node_model_defines_expected_fields():
    content = _read("netbox_proxbox/models/proxmox_node.py")
    assert "class ProxmoxNode" in content
    assert "netbox_device" in content
    assert "proxmox_cluster" in content
    assert "ip_address" in content
    assert "online" in content
    assert "cpu_usage" in content
    assert "memory_usage" in content
    assert "memory_usage_percent" in content


def test_proxmox_node_model_links_to_dcim_device():
    content = _read("netbox_proxbox/models/proxmox_node.py")
    assert "dcim.Device" in content or "dcim" in content


def test_proxmox_cluster_model_links_to_netbox_cluster():
    content = _read("netbox_proxbox/models/proxmox_cluster.py")
    assert "virtualization.Cluster" in content or "virtualization" in content


def test_cluster_nodes_template_exists():
    path = (
        REPO_ROOT
        / "netbox_proxbox/templates/netbox_proxbox/proxmoxendpoint_cluster_nodes.html"
    )
    assert path.exists()


def test_cluster_nodes_template_renders_node_table():
    content = _read(
        "netbox_proxbox/templates/netbox_proxbox/proxmoxendpoint_cluster_nodes.html"
    )
    assert "node" in content.lower()
    assert "cluster" in content.lower()


def test_proxmoxendpoint_template_has_mode_badges():
    content = _read("netbox_proxbox/templates/netbox_proxbox/proxmoxendpoint.html")
    # Mode badges should now exist (not just "undefined")
    assert "cluster" in content.lower()
    assert "standalone" in content.lower()


def test_migration_0016_exists():
    path = REPO_ROOT / "netbox_proxbox/migrations/0016_proxmox_cluster_node_models.py"
    assert path.exists()


def test_migration_0016_creates_both_tables():
    content = _read("netbox_proxbox/migrations/0016_proxmox_cluster_node_models.py")
    assert "proxmoxcluster" in content.lower()
    assert "proxmoxnode" in content.lower()


def test_models_init_exports_cluster_and_node():
    content = _read("netbox_proxbox/models/__init__.py")
    assert "ProxmoxCluster" in content
    assert "ProxmoxNode" in content
