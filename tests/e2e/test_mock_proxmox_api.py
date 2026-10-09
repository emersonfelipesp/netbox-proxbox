"""Domain and standalone launcher compatibility for the local Proxmox mock."""

from collections.abc import Iterator
import copy
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from types import ModuleType

import httpx
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def mock_module(monkeypatch: pytest.MonkeyPatch) -> Iterator[ModuleType]:
    """Isolate mutable VM state and prevent remote telemetry in domain tests."""
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
    from tests.e2e import mock_proxmox_api

    previous = copy.deepcopy(mock_proxmox_api.VM_RESOURCES)
    yield mock_proxmox_api
    mock_proxmox_api.VM_RESOURCES.clear()
    mock_proxmox_api.VM_RESOURCES.update(previous)


def test_domain_routes_and_shared_vm_state(mock_module: ModuleType) -> None:
    """Preserve read envelopes and admin changes across factory instances."""
    first = mock_module.create_app()
    second = mock_module.create_app()
    with TestClient(first) as client, TestClient(second) as other:
        assert client.get("/api2/json/version").json() == {
            "data": {"release": "8.2", "repoid": "mock"}
        }
        update = client.post("/__admin/vm/101/status", json={"status": " STOPPED "})
        assert update.json() == {"ok": True, "vmid": 101, "status": "stopped"}
        resources = other.get("/api2/json/cluster/resources").json()["data"]
        assert (
            next(item for item in resources if item.get("vmid") == 101)["status"]
            == "stopped"
        )
        assert client.post(
            "/__admin/vm/999/status", json={"status": "running"}
        ).json() == {
            "ok": False,
            "detail": "vmid not found",
        }
        assert client.post("/__admin/vm/101/status", json={}).status_code == 422
        assert (
            other.get("/api2/json/nodes/pve01/qemu/101/config").json()["data"]["name"]
            == "e2e-qemu-101"
        )
        assert (
            other.get("/api2/json/nodes/pve01/lxc/102/config").json()["data"][
                "hostname"
            ]
            == "e2e-lxc-102"
        )


def test_backup_filtering_and_factory_operation_identity(
    mock_module: ModuleType,
) -> None:
    """Keep storage filtering, task responses and stable route operation IDs."""
    first = mock_module.create_app()
    second = mock_module.create_app()
    assert first.openapi()["paths"] == second.openapi()["paths"]
    assert first.openapi()["paths"] == mock_module.app.openapi()["paths"]
    with TestClient(first) as client:
        path = "/api2/json/nodes/pve01/storage/backup/content"
        backups = client.get(path, params={"content": "backup"}).json()["data"]
        assert {item["vmid"] for item in backups} == {101, 102}
        assert client.get(path, params={"content": "backup", "vmid": 102}).json()[
            "data"
        ] == [next(item for item in backups if item["vmid"] == 102)]
        assert client.get(path, params={"content": "images"}).json() == {"data": []}
        task = client.get("/api2/json/nodes/pve01/tasks").json()["data"][0]
        assert client.get(
            f"/api2/json/nodes/pve01/tasks/{task['upid']}/status"
        ).json() == {"data": {"status": "stopped", "exitstatus": "OK"}}


def _wait_for_version(
    process: subprocess.Popen[str], client: httpx.Client, port: int, log_path: Path
) -> httpx.Response:
    """Wait for a bounded local readiness response or explain startup failure."""
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if process.poll() is not None:
            pytest.fail(log_path.read_text())
        try:
            return client.get(f"http://127.0.0.1:{port}/api2/json/version")
        except httpx.ConnectError:
            time.sleep(0.05)
    pytest.fail("Local mock did not become ready: " + log_path.read_text())


def test_standalone_script_launcher(tmp_path: Path) -> None:
    """Start the documented script entry point and verify graceful shutdown."""
    script = Path(__file__).with_name("mock_proxmox_api.py")
    environment = {
        key: value for key, value in os.environ.items() if not key.startswith("OTEL_")
    }
    environment["OTEL_SDK_DISABLED"] = "true"
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    log_path = tmp_path / "mock.log"
    with log_path.open("w") as log:
        process = subprocess.Popen(
            [sys.executable, str(script), "--host", "127.0.0.1", "--port", str(port)],
            env=environment,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        try:
            with httpx.Client(timeout=1) as client:
                response = _wait_for_version(process, client, port, log_path)
            assert response.status_code == 200
            assert response.json() == {"data": {"release": "8.2", "repoid": "mock"}}
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
    assert "Application shutdown complete" in log_path.read_text()
