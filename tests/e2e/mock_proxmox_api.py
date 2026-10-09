"""Tests for mock_proxmox_api."""

from __future__ import annotations

import argparse
import os
from typing import TYPE_CHECKING

from fastapi import APIRouter, FastAPI, Query
from fastapi.telemetry import TelemetryConfig
from pydantic import BaseModel

if TYPE_CHECKING or __package__:
    from .mock_telemetry import configure_telemetry_privacy
else:
    from mock_telemetry import configure_telemetry_privacy

router = APIRouter()


VM_RESOURCES: dict[int, dict] = {
    101: {
        "type": "qemu",
        "vmid": 101,
        "name": "e2e-qemu-101",
        "node": "pve01",
        "status": "running",
        "maxcpu": 2,
        "maxmem": 2147483648,
        "maxdisk": 21474836480,
    },
    102: {
        "type": "lxc",
        "vmid": 102,
        "name": "e2e-lxc-102",
        "node": "pve01",
        "status": "running",
        "maxcpu": 1,
        "maxmem": 1073741824,
        "maxdisk": 10737418240,
    },
}


class VmStatusUpdate(BaseModel):
    status: str


def _ok(data):
    return {"data": data}


@router.get("/api2/json/version")
def version():
    return _ok({"release": "8.2", "repoid": "mock"})


@router.get("/api2/json/cluster/status")
def cluster_status():
    return _ok(
        [
            {"type": "cluster", "name": "e2e-cluster", "version": 1},
            {
                "type": "node",
                "name": "pve01",
                "nodeid": 1,
                "ip": "10.10.10.11",
                "online": 1,
                "local": 1,
                "level": "",
            },
        ]
    )


@router.get("/api2/json/cluster/config/join")
def cluster_config_join():
    return _ok(
        {
            "nodelist": [
                {
                    "name": "pve01",
                    "nodeid": 1,
                    "pve_fp": "AA:BB:CC:DD:EE:FF:00:11:22:33:44:55:66:77:88:99:AA:BB:CC:DD:EE:FF:00:11:22:33:44:55:66:77:88:99",
                }
            ]
        }
    )


@router.get("/api2/json/cluster/resources")
def cluster_resources():
    resources = [{"type": "node", "node": "pve01", "status": "online", "maxcpu": 8}]
    resources.extend(VM_RESOURCES.values())
    return _ok(resources)


@router.post("/__admin/vm/{vmid}/status")
def set_vm_status(vmid: int, body: VmStatusUpdate):
    vm = VM_RESOURCES.get(vmid)
    if vm is None:
        return {"ok": False, "detail": "vmid not found"}
    vm["status"] = body.status.strip().lower()
    return {"ok": True, "vmid": vmid, "status": vm["status"]}


@router.get("/api2/json/storage")
def storage_list():
    return _ok(
        [
            {
                "storage": "local",
                "type": "dir",
                "content": "images,rootdir",
                "shared": 0,
                "nodes": "pve01",
            },
            {
                "storage": "backup",
                "type": "dir",
                "content": "backup",
                "shared": 1,
                "nodes": "pve01",
            },
        ]
    )


@router.get("/api2/json/nodes/{node}/qemu/{vmid}/config")
def qemu_config(node: str, vmid: int):
    return _ok(
        {
            "name": f"e2e-qemu-{vmid}",
            "onboot": 1,
            "agent": 1,
            "searchdomain": "lab.local",
            "scsi0": "local-lvm:vm-101-disk-0,size=20G",
            "sockets": 1,
            "cores": 2,
            "memory": 2048,
            "node": node,
        }
    )


@router.get("/api2/json/nodes/{node}/lxc/{vmid}/config")
def lxc_config(node: str, vmid: int):
    return _ok(
        {
            "hostname": f"e2e-lxc-{vmid}",
            "onboot": 1,
            "unprivileged": 1,
            "rootfs": "local-lvm:subvol-102-disk-0,size=10G",
            "cores": 1,
            "memory": 1024,
            "node": node,
        }
    )


@router.get("/api2/json/nodes/{node}/storage/{storage}/content")
def storage_content(
    node: str,
    storage: str,
    content: str | None = Query(default=None),
    vmid: int | None = Query(default=None),
):
    if content == "backup":
        items = [
            {
                "content": "backup",
                "vmid": 101,
                "volid": "backup:101/vzdump-qemu-101-2026_01_01-00_00_00.vma.zst",
                "size": 10485760,
                "ctime": 1767225600,
                "format": "tzst",
                "subtype": "qemu",
                "notes": "e2e backup qemu",
                "node": node,
                "storage": storage,
            },
            {
                "content": "backup",
                "vmid": 102,
                "volid": "backup:102/vzdump-lxc-102-2026_01_01-00_00_00.tar.zst",
                "size": 7340032,
                "ctime": 1767225600,
                "format": "tzst",
                "subtype": "lxc",
                "notes": "e2e backup lxc",
                "node": node,
                "storage": storage,
            },
        ]
        if vmid is not None:
            items = [item for item in items if item["vmid"] == vmid]
        return _ok(items)
    return _ok([])


@router.get("/api2/json/nodes/{node}/tasks")
def tasks(node: str, source: str | None = Query(default=None)):
    _ = source
    return _ok(
        [
            {
                "upid": f"UPID:{node}:00000001:00000001:00000001:qmstart:101:root@pam:",
                "node": node,
                "pid": 1,
                "pstart": 1,
                "id": "101",
                "type": "qmstart",
                "user": "root@pam",
                "starttime": 1767225600,
                "endtime": 1767225602,
                "status": "OK",
            }
        ]
    )


@router.get("/api2/json/nodes/{node}/tasks/{upid}/status")
def task_status(node: str, upid: str):
    _ = (node, upid)
    return _ok({"status": "stopped", "exitstatus": "OK"})


@router.get("/api2/json/nodes/{node}/qemu/{vmid}/snapshot")
def qemu_snapshot(node: str, vmid: int):
    return _ok(
        [
            {
                "name": "base",
                "description": "e2e qemu snapshot",
                "snaptime": 1767225600,
                "vmstate": 0,
                "parent": None,
                "vmid": vmid,
                "node": node,
            }
        ]
    )


@router.get("/api2/json/nodes/{node}/lxc/{vmid}/snapshot")
def lxc_snapshot(node: str, vmid: int):
    return _ok(
        [
            {
                "name": "base",
                "description": "e2e lxc snapshot",
                "snaptime": 1767225600,
                "vmstate": 0,
                "parent": None,
                "vmid": vmid,
                "node": node,
            }
        ]
    )


def create_app(*, telemetry: TelemetryConfig | None = None) -> FastAPI:
    """Create the public E2E mock with operator-configured native telemetry."""
    configuration: TelemetryConfig = telemetry.copy() if telemetry is not None else {}
    configuration.setdefault(
        "auto_configure", os.getenv("FASTAPI_OTEL_AUTO_CONFIGURE", "").lower() == "true"
    )
    if os.getenv("OTEL_SDK_DISABLED", "").lower() == "true":
        configuration.update(
            {"auto_configure": False, "tracing": False, "metrics": False, "logs": False}
        )
    configure_telemetry_privacy(configuration)
    application = FastAPI(title="proxmox-mock", telemetry=configuration)
    application.include_router(router)
    return application


app = create_app()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run local Proxmox mock API service")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8006)
    args = parser.parse_args()

    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
