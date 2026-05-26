"""Tests for test_schemas."""

from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest


def _load_schema_module():
    repo_root = Path(__file__).resolve().parents[1]
    stub = types.ModuleType("netbox_proxbox")
    stub.__path__ = [str(repo_root / "netbox_proxbox")]
    original = sys.modules.get("netbox_proxbox")
    sys.modules["netbox_proxbox"] = stub
    try:
        return importlib.import_module("netbox_proxbox.schemas")
    finally:
        if original is None:
            sys.modules.pop("netbox_proxbox", None)
        else:
            sys.modules["netbox_proxbox"] = original


schemas = _load_schema_module()

BackendRequestContext = schemas.BackendRequestContext
OpenAPISummary = schemas.OpenAPISummary
ProxmoxClusterStatusResponse = schemas.ProxmoxClusterStatusResponse
ProxmoxStorageRecord = schemas.ProxmoxStorageRecord
ProxmoxVMConfig = schemas.ProxmoxVMConfig
ProxmoxNodeRow = schemas.ProxmoxNodeRow
SyncJobData = schemas.SyncJobData


def test_proxmox_vm_config_coerces_strings_and_formats_memory():
    config = ProxmoxVMConfig.model_validate(
        {"onboot": "1", "agent": "0", "memory": "2048", "cores": "4"}
    )

    assert config.onboot is True
    assert config.agent is False
    assert config.memory == 2048
    assert config.cores == 4
    assert config.memory_display == "2048 MiB (2.00 GiB)"


def test_proxmox_vm_config_classifies_config_sections():
    config = ProxmoxVMConfig.model_validate({})
    disks, networks, advanced = config.flatten_sections(
        {
            "scsi0": "local-lvm:vm-100-disk-0",
            "net0": "virtio=AA:BB:CC:DD:EE:FF",
            "balloon": 0,
        }
    )

    assert disks == [("scsi0", "local-lvm:vm-100-disk-0")]
    assert networks == [("net0", "virtio=AA:BB:CC:DD:EE:FF")]
    assert advanced == [("balloon", 0)]


def test_cluster_status_response_wraps_list_payload():
    response = ProxmoxClusterStatusResponse.model_validate(
        [
            {"type": "cluster", "name": "pve", "nodes": "2", "quorate": "1"},
            {"type": "node", "name": "node-1", "online": "1"},
            {"type": "node", "name": "node-2", "online": "0"},
        ]
    )

    assert response.cluster_record is not None
    assert response.cluster_record.name == "pve"
    assert len(response.node_records) == 2


def test_proxmox_node_row_builds_from_persisted_node_model():
    node = SimpleNamespace(
        name="pve-02",
        online=True,
        cpu_usage=0.125,
        max_cpu=8,
        memory_usage=16 * 1024**3,
        max_memory=64 * 1024**3,
        support_level="enterprise",
    )

    row = ProxmoxNodeRow.from_node_model(node)

    assert row.name == "pve-02"
    assert row.status == "online"
    assert row.cpu_pct == 12.5
    assert row.cpu_label == "12.50% (8 CPUs)"
    assert row.uptime == "—"
    assert row.loadavg == "—"
    assert row.memory_label == "16.00 GiB / 64.00 GiB"
    assert row.disk_label == "—"


def test_storage_record_computes_effective_usage():
    record = ProxmoxStorageRecord.model_validate({"maxdisk": 100, "disk": 40})

    assert record.effective_total == 100
    assert record.effective_used == 40
    assert record.to_usage_dict().used_pct == 40.0


def test_openapi_summary_from_raw_payload_normalizes_content():
    summary = OpenAPISummary.from_raw_payload(
        {
            "info": {"title": "ProxBox API", "version": "0.1.0"},
            "servers": [{"url": "https://proxbox.local", "description": "Primary"}],
            "tags": [{"name": "health"}],
            "paths": {
                "/health": {
                    "get": {
                        "summary": "Health",
                        "parameters": [{"name": "verbose"}],
                        "responses": {"200": {"description": "ok"}},
                    }
                }
            },
            "components": {
                "securitySchemes": {
                    "bearerAuth": {"type": "http", "scheme": "bearer", "in": "header"}
                },
                "schemas": {"Health": {"type": "object"}},
            },
        }
    )

    assert summary.stats.operations == 1
    assert summary.servers[0].url == "https://proxbox.local"
    assert summary.security_schemes[0].name == "bearerAuth"


def test_openapi_summary_rejects_non_object_payload():
    with pytest.raises(ValueError):
        OpenAPISummary.from_raw_payload("not a dict")


def test_sync_job_data_from_job_reads_nested_params():
    job = SimpleNamespace(
        data={
            "proxbox_sync": {
                "params": {
                    "sync_types": ["all"],
                    "netbox_vm_ids": ["1"],
                    "run_id": "issue-519-run",
                }
            }
        }
    )

    data = SyncJobData.from_job(job)
    assert data.params.sync_types == ["all"]
    assert data.params.netbox_vm_ids == ["1"]
    assert data.params.run_id == "issue-519-run"


def test_backend_request_context_defaults_headers():
    ctx = BackendRequestContext(http_url="http://x:8000", verify_ssl=False)

    assert ctx.http_url == "http://x:8000"
    assert ctx.verify_ssl is False
    assert ctx.headers == {}


def test_schema_import_smoke():
    assert ProxmoxVMConfig is not None
