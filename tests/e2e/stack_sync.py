from __future__ import annotations

import json
import time
from collections.abc import Iterable
from typing import Any

import requests

from stack_common import (
    assert_ok,
    extract_id,
    extract_status_value,
    get_vm_by_proxmox_vmid,
    list_records,
    require_one,
    snapshot_proxbox_job_ids,
)


def trigger_and_wait_sync(
    netbox_base_url: str,
    netbox_token: str,
    *,
    route: str,
    expected_name_fragment: str,
) -> dict[str, Any]:
    headers = {
        "Authorization": f"Token {netbox_token}",
        "Accept": "application/json",
    }
    seen_job_ids = snapshot_proxbox_job_ids(netbox_base_url, netbox_token)

    # Django's CSRF middleware requires a CSRF token for POST to non-DRF views.
    # Fetch the csrftoken cookie from the login page then echo it via X-CSRFToken.
    _csrf = requests.get(f"{netbox_base_url}/login/", timeout=10)
    csrftoken = _csrf.cookies.get("csrftoken", "")
    trigger_headers = {**headers, "X-CSRFToken": csrftoken}
    trigger_cookies = {"csrftoken": csrftoken} if csrftoken else {}

    trigger = requests.post(
        f"{netbox_base_url}{route}",
        headers=trigger_headers,
        cookies=trigger_cookies,
        timeout=30,
        allow_redirects=False,
    )
    if trigger.status_code not in (302, 303):
        raise AssertionError(
            f"Sync trigger {route} did not redirect as expected: HTTP {trigger.status_code} {trigger.text}"
        )

    jobs_url = f"{netbox_base_url}/api/core/jobs/?limit=50"
    deadline = time.time() + 600
    terminal_statuses = {"completed", "errored", "failed"}
    expected_lower = expected_name_fragment.strip().lower()

    while time.time() < deadline:
        jobs_response = requests.get(jobs_url, headers=headers, timeout=30)
        jobs_payload = assert_ok(jobs_response, context="list jobs")
        results: Iterable[dict[str, Any]] = jobs_payload.get("results", [])
        proxbox_jobs = [
            job
            for job in results
            if str(job.get("name", "")).startswith("Proxbox Sync")
        ]
        for job in proxbox_jobs:
            job_id = extract_id(job.get("id"))
            if job_id is None or job_id in seen_job_ids:
                continue
            name = str(job.get("name", "")).lower()
            if expected_lower and expected_lower not in name:
                continue
            status = extract_status_value(job.get("status"))
            if status in terminal_statuses:
                if status != "completed":
                    raise AssertionError(
                        f"Proxbox sync job for {route} failed with status={status}: {job}"
                    )
                return job
        time.sleep(5)

    raise AssertionError(
        f"Timed out waiting for Proxbox sync job completion for route={route}"
    )


def assert_devices_sync_data(netbox_base_url: str, netbox_token: str) -> dict[str, int]:
    headers = {"Authorization": f"Token {netbox_token}"}

    cluster_types = list_records(
        f"{netbox_base_url}/api/virtualization/cluster-types/",
        headers,
        context="cluster types",
        params={"slug": "cluster", "limit": 10},
    )
    cluster_type = require_one(
        cluster_types, label="cluster type", key="slug", value="cluster"
    )

    clusters = list_records(
        f"{netbox_base_url}/api/virtualization/clusters/",
        headers,
        context="clusters",
        params={"name": "e2e-cluster", "limit": 10},
    )
    cluster = require_one(clusters, label="cluster", key="name", value="e2e-cluster")
    cluster_type_id = extract_id(cluster.get("type"))
    if cluster_type_id != extract_id(cluster_type.get("id")):
        raise AssertionError(
            f"Cluster type mismatch for e2e-cluster: {cluster.get('type')}"
        )

    sites = list_records(
        f"{netbox_base_url}/api/dcim/sites/",
        headers,
        context="sites",
        params={"name": "Proxmox Default Site - e2e-cluster", "limit": 10},
    )
    site = require_one(
        sites,
        label="site",
        key="name",
        value="Proxmox Default Site - e2e-cluster",
    )

    manufacturers = list_records(
        f"{netbox_base_url}/api/dcim/manufacturers/",
        headers,
        context="manufacturers",
        params={"slug": "proxmox", "limit": 10},
    )
    require_one(manufacturers, label="manufacturer", key="slug", value="proxmox")

    device_types = list_records(
        f"{netbox_base_url}/api/dcim/device-types/",
        headers,
        context="device types",
        params={"model": "Proxmox Generic Device", "limit": 10},
    )
    require_one(
        device_types,
        label="device type",
        key="model",
        value="Proxmox Generic Device",
    )

    device_roles = list_records(
        f"{netbox_base_url}/api/dcim/device-roles/",
        headers,
        context="device roles",
        params={"slug": "proxmox-node", "limit": 10},
    )
    require_one(device_roles, label="device role", key="slug", value="proxmox-node")

    devices = list_records(
        f"{netbox_base_url}/api/dcim/devices/",
        headers,
        context="devices",
        params={"name": "pve01", "limit": 20},
    )
    device = require_one(devices, label="device", key="name", value="pve01")
    if extract_id(device.get("cluster")) != extract_id(cluster.get("id")):
        raise AssertionError("Device pve01 is not linked to e2e-cluster")
    if extract_id(device.get("site")) != extract_id(site.get("id")):
        raise AssertionError("Device pve01 is not linked to expected default site")

    return {
        "cluster_id": int(extract_id(cluster.get("id")) or 0),
        "site_id": int(extract_id(site.get("id")) or 0),
        "device_id": int(extract_id(device.get("id")) or 0),
    }


def assert_storage_sync_data(
    netbox_base_url: str, netbox_token: str, cluster_id: int
) -> None:
    headers = {"Authorization": f"Token {netbox_token}"}
    storage_records = list_records(
        f"{netbox_base_url}/api/plugins/proxbox/storage/",
        headers,
        context="storage records",
        params={"limit": 50},
    )
    if len(storage_records) < 2:
        raise AssertionError(
            f"Expected at least 2 storage records, got {len(storage_records)}"
        )

    by_name = {str(record.get("name")): record for record in storage_records}
    for expected_name in ("local", "backup"):
        if expected_name not in by_name:
            raise AssertionError(f"Missing expected storage record: {expected_name}")
        record = by_name[expected_name]
        if extract_id(record.get("cluster")) != cluster_id:
            raise AssertionError(
                f"Storage {expected_name} not linked to expected cluster id={cluster_id}"
            )

    backup_storage = by_name["backup"]
    if backup_storage.get("shared") is not True:
        raise AssertionError(
            f"Expected backup storage shared=true, got {backup_storage.get('shared')}"
        )
    if backup_storage.get("enabled") is not True:
        raise AssertionError(
            f"Expected backup storage enabled=true, got {backup_storage.get('enabled')}"
        )


def assert_virtual_machines_sync_data(
    netbox_base_url: str,
    netbox_token: str,
    *,
    cluster_id: int,
    device_id: int,
) -> dict[int, int]:
    vm_101 = get_vm_by_proxmox_vmid(netbox_base_url, netbox_token, 101)
    vm_102 = get_vm_by_proxmox_vmid(netbox_base_url, netbox_token, 102)

    if extract_status_value(vm_101.get("status")) != "active":
        raise AssertionError(
            f"Expected VM 101 status active, got {vm_101.get('status')}"
        )
    if extract_status_value(vm_102.get("status")) != "active":
        raise AssertionError(
            f"Expected VM 102 status active, got {vm_102.get('status')}"
        )

    for vm in (vm_101, vm_102):
        if extract_id(vm.get("cluster")) != cluster_id:
            raise AssertionError(
                f"VM {vm.get('name')} is not linked to expected cluster"
            )
        if extract_id(vm.get("device")) != device_id:
            raise AssertionError(
                f"VM {vm.get('name')} is not linked to expected device"
            )

    vm_101_cf = vm_101.get("custom_fields") or {}
    vm_102_cf = vm_102.get("custom_fields") or {}
    if vm_101_cf.get("proxmox_vm_id") not in (None, 101):
        raise AssertionError(
            f"Unexpected VM 101 custom field proxmox_vm_id={vm_101_cf.get('proxmox_vm_id')}"
        )
    if vm_102_cf.get("proxmox_vm_id") not in (None, 102):
        raise AssertionError(
            f"Unexpected VM 102 custom field proxmox_vm_id={vm_102_cf.get('proxmox_vm_id')}"
        )

    return {
        101: int(extract_id(vm_101.get("id")) or 0),
        102: int(extract_id(vm_102.get("id")) or 0),
    }


def assert_virtual_disks_sync_data(
    netbox_base_url: str,
    netbox_token: str,
    *,
    vm_ids_by_vmid: dict[int, int],
) -> None:
    headers = {"Authorization": f"Token {netbox_token}"}
    disks = list_records(
        f"{netbox_base_url}/api/virtualization/virtual-disks/",
        headers,
        context="virtual disks",
        params={"limit": 200},
    )
    if len(disks) < 2:
        raise AssertionError(f"Expected at least 2 virtual disks, got {len(disks)}")

    disk_vm_ids = {
        extract_id(disk.get("virtual_machine"))
        for disk in disks
        if extract_id(disk.get("virtual_machine")) is not None
    }
    for vmid, vm_id in vm_ids_by_vmid.items():
        if vm_id not in disk_vm_ids:
            raise AssertionError(
                f"No virtual disks found for VM vmid={vmid} id={vm_id}"
            )


def assert_backups_sync_data(
    netbox_base_url: str,
    netbox_token: str,
    *,
    vm_ids_by_vmid: dict[int, int],
) -> None:
    headers = {"Authorization": f"Token {netbox_token}"}
    backups = list_records(
        f"{netbox_base_url}/api/plugins/proxbox/backups/",
        headers,
        context="backup records",
        params={"limit": 200},
    )
    expected = {
        "backup:101/vzdump-qemu-101-2026_01_01-00_00_00.vma.zst": 101,
        "backup:102/vzdump-lxc-102-2026_01_01-00_00_00.tar.zst": 102,
    }
    for volume_id, vmid in expected.items():
        record = require_one(backups, label="backup", key="volume_id", value=volume_id)
        if int(record.get("vmid") or -1) != vmid:
            raise AssertionError(
                f"Backup {volume_id} has vmid={record.get('vmid')} expected={vmid}"
            )
        if extract_id(record.get("virtual_machine")) != vm_ids_by_vmid[vmid]:
            raise AssertionError(
                f"Backup {volume_id} linked to unexpected virtual_machine={record.get('virtual_machine')}"
            )
        if extract_id(record.get("proxmox_storage")) is None:
            raise AssertionError(f"Backup {volume_id} missing proxmox_storage relation")


def assert_snapshots_sync_data(
    netbox_base_url: str,
    netbox_token: str,
    *,
    vm_ids_by_vmid: dict[int, int],
) -> None:
    headers = {"Authorization": f"Token {netbox_token}"}
    snapshots = list_records(
        f"{netbox_base_url}/api/plugins/proxbox/snapshots/",
        headers,
        context="snapshot records",
        params={"limit": 200},
    )

    expected_snapshots = {
        (101, "base", "pve01", "qemu"),
        (102, "base", "pve01", "lxc"),
    }
    seen: set[tuple[int, str, str, str]] = set()
    for record in snapshots:
        vmid = int(record.get("vmid") or -1)
        key = (
            vmid,
            str(record.get("name") or ""),
            str(record.get("node") or ""),
            str(record.get("subtype") or ""),
        )
        if key not in expected_snapshots:
            continue
        if extract_id(record.get("virtual_machine")) != vm_ids_by_vmid[vmid]:
            raise AssertionError(
                f"Snapshot relation mismatch for vmid={vmid}: {record}"
            )
        status = extract_status_value(record.get("status"))
        if status != "active":
            raise AssertionError(
                f"Expected active snapshot status for vmid={vmid}, got {status}"
            )
        seen.add(key)

    missing = expected_snapshots - seen
    if missing:
        raise AssertionError(f"Missing expected snapshots: {sorted(missing)}")


def assert_task_history_sync_data(
    netbox_base_url: str,
    netbox_token: str,
    *,
    vm_id_101: int,
) -> None:
    headers = {"Authorization": f"Token {netbox_token}"}
    records = list_records(
        f"{netbox_base_url}/api/plugins/proxbox/task-history/",
        headers,
        context="task history records",
        params={"limit": 200},
    )
    if not records:
        raise AssertionError("Expected task history records after full-update stream")

    linked_to_vm_101 = False
    for record in records:
        upid = str(record.get("upid") or "")
        if not upid.startswith("UPID:"):
            raise AssertionError(f"Unexpected task history UPID format: {upid!r}")
        if not str(record.get("node") or ""):
            raise AssertionError(f"Task history record missing node: {record}")
        if not str(record.get("task_type") or ""):
            raise AssertionError(f"Task history record missing task_type: {record}")
        if not str(record.get("status") or ""):
            raise AssertionError(f"Task history record missing status: {record}")
        if extract_id(record.get("virtual_machine")) == vm_id_101:
            linked_to_vm_101 = True

    if not linked_to_vm_101:
        raise AssertionError("Expected at least one task history linked to VM 101")


def set_mock_vm_status(mock_base_url: str, vmid: int, status: str) -> None:
    response = requests.post(
        f"{mock_base_url}/__admin/vm/{vmid}/status",
        json={"status": status},
        timeout=15,
    )
    payload = assert_ok(response, context=f"set proxmox mock vm status vmid={vmid}")
    if payload.get("ok") is not True:
        raise AssertionError(f"Failed updating proxmox mock VM status: {payload}")


def assert_vm_status_transition(
    netbox_base_url: str,
    netbox_token: str,
    proxmox_mock_base_url: str,
) -> None:
    vm = get_vm_by_proxmox_vmid(netbox_base_url, netbox_token, 101)
    initial_status = extract_status_value(vm.get("status"))
    if initial_status != "active":
        raise AssertionError(
            f"Expected initial VM status active for vmid=101, got {initial_status!r}"
        )

    set_mock_vm_status(proxmox_mock_base_url, 101, "stopped")
    trigger_and_wait_sync(
        netbox_base_url,
        netbox_token,
        route="/plugins/proxbox/sync/full-update/",
        expected_name_fragment="full update",
    )

    updated_vm = get_vm_by_proxmox_vmid(netbox_base_url, netbox_token, 101)
    updated_status = extract_status_value(updated_vm.get("status"))
    if updated_status != "offline":
        raise AssertionError(
            f"Expected updated VM status offline for vmid=101, got {updated_status!r}"
        )


def assert_backend_stream(proxbox_base_url: str) -> dict[str, Any]:
    complete_payload: dict[str, Any] | None = None
    with requests.get(
        f"{proxbox_base_url}/full-update/stream",
        timeout=(10, 300),
        stream=True,
    ) as response:
        if response.status_code >= 400:
            raise AssertionError(
                f"proxbox-api full-update stream failed: HTTP {response.status_code} {response.text}"
            )
        for raw_line in response.iter_lines(decode_unicode=True):
            if not raw_line:
                continue
            line = raw_line.strip()
            if line.startswith("data:"):
                data_text = line[5:].strip()
                try:
                    payload = json.loads(data_text)
                except json.JSONDecodeError:
                    continue
                if isinstance(payload, dict) and "ok" in payload:
                    complete_payload = payload

    if not complete_payload:
        raise AssertionError(
            "Did not receive a complete payload from /full-update/stream"
        )
    if complete_payload.get("ok") is not True:
        raise AssertionError(
            f"full-update stream completed with failure: {complete_payload}"
        )

    result = complete_payload.get("result")
    if not isinstance(result, dict):
        raise AssertionError(
            f"full-update stream payload missing result object: {complete_payload}"
        )

    required_count_keys = (
        "devices_count",
        "storage_count",
        "virtual_machines_count",
        "virtual_disks_count",
        "task_history_count",
        "backups_count",
        "snapshots_count",
    )
    for key in required_count_keys:
        value = result.get(key)
        if not isinstance(value, int):
            raise AssertionError(
                f"full-update stream result missing int {key}: {result}"
            )

    if int(result.get("task_history_count", 0)) < 1:
        raise AssertionError(f"Expected task_history_count >= 1, got {result}")

    return complete_payload


def run_and_assert_all_sync_operations(
    netbox_base_url: str,
    netbox_token: str,
    proxmox_mock_base_url: str,
) -> None:
    trigger_and_wait_sync(
        netbox_base_url,
        netbox_token,
        route="/plugins/proxbox/sync/devices/",
        expected_name_fragment="devices",
    )
    device_refs = assert_devices_sync_data(netbox_base_url, netbox_token)

    trigger_and_wait_sync(
        netbox_base_url,
        netbox_token,
        route="/plugins/proxbox/sync/storage/",
        expected_name_fragment="storage",
    )
    assert_storage_sync_data(
        netbox_base_url,
        netbox_token,
        cluster_id=device_refs["cluster_id"],
    )

    trigger_and_wait_sync(
        netbox_base_url,
        netbox_token,
        route="/plugins/proxbox/sync/virtual-machines/",
        expected_name_fragment="virtual machines",
    )
    vm_ids_by_vmid = assert_virtual_machines_sync_data(
        netbox_base_url,
        netbox_token,
        cluster_id=device_refs["cluster_id"],
        device_id=device_refs["device_id"],
    )

    trigger_and_wait_sync(
        netbox_base_url,
        netbox_token,
        route="/plugins/proxbox/sync/virtual-machines/virtual-disks/",
        expected_name_fragment="virtual disks",
    )
    assert_virtual_disks_sync_data(
        netbox_base_url,
        netbox_token,
        vm_ids_by_vmid=vm_ids_by_vmid,
    )

    trigger_and_wait_sync(
        netbox_base_url,
        netbox_token,
        route="/plugins/proxbox/sync/virtual-machines/backups/",
        expected_name_fragment="vm backups",
    )
    assert_backups_sync_data(
        netbox_base_url,
        netbox_token,
        vm_ids_by_vmid=vm_ids_by_vmid,
    )

    trigger_and_wait_sync(
        netbox_base_url,
        netbox_token,
        route="/plugins/proxbox/sync/virtual-machines/snapshots/",
        expected_name_fragment="vm snapshots",
    )
    assert_snapshots_sync_data(
        netbox_base_url,
        netbox_token,
        vm_ids_by_vmid=vm_ids_by_vmid,
    )

    trigger_and_wait_sync(
        netbox_base_url,
        netbox_token,
        route="/plugins/proxbox/sync/full-update/",
        expected_name_fragment="full update",
    )
    assert_vm_status_transition(netbox_base_url, netbox_token, proxmox_mock_base_url)
