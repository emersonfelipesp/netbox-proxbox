from __future__ import annotations

import json
import os
import time
from collections.abc import Iterable
from typing import Any

import requests


def _must_getenv(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _wait_http_ok(url: str, *, timeout_seconds: int = 300) -> None:
    deadline = time.time() + timeout_seconds
    last_error = ""
    while time.time() < deadline:
        try:
            response = requests.get(url, timeout=5)
            if response.status_code < 500:
                return
            last_error = f"HTTP {response.status_code}"
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
        time.sleep(2)
    raise RuntimeError(f"Timed out waiting for {url}: {last_error}")


def _assert_ok(response: requests.Response, *, context: str) -> dict:
    if response.status_code >= 400:
        raise AssertionError(
            f"{context} failed: HTTP {response.status_code} - {response.text}"
        )
    try:
        return response.json()
    except Exception as exc:  # noqa: BLE001
        raise AssertionError(f"{context} did not return JSON: {exc}") from exc


def _extract_id(value: Any) -> int | None:
    if isinstance(value, dict):
        nested_id = value.get("id")
        if isinstance(nested_id, int):
            return nested_id
        if isinstance(nested_id, str) and nested_id.isdigit():
            return int(nested_id)
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _list_records(
    url: str,
    headers: dict,
    *,
    context: str,
    params: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    response = requests.get(url, headers=headers, params=params, timeout=30)
    payload = _assert_ok(response, context=context)
    results = payload.get("results")
    if not isinstance(results, list):
        raise AssertionError(f"{context} response missing results[]: {payload}")
    return [record for record in results if isinstance(record, dict)]


def _require_one(
    records: list[dict[str, Any]],
    *,
    label: str,
    key: str,
    value: Any,
) -> dict[str, Any]:
    for record in records:
        if record.get(key) == value:
            return record
    raise AssertionError(f"Missing {label}: expected {key}={value!r}")


def _post_json(url: str, payload: dict, headers: dict, *, context: str) -> dict:
    response = requests.post(url, json=payload, headers=headers, timeout=30)
    return _assert_ok(response, context=context)


def _ensure_proxbox_backend_endpoints(
    proxbox_base_url: str,
    netbox_public_url: str,
    netbox_token: str,
) -> None:
    # netbox endpoint (backend database)
    netbox_payload = {
        "name": "netbox",
        "ip_address": "netbox",
        "domain": "netbox",
        "port": 8080,
        "token_version": "v1",
        "token": netbox_token,
        "verify_ssl": False,
    }
    resp = requests.post(
        f"{proxbox_base_url}/netbox/endpoint", json=netbox_payload, timeout=30
    )
    if (
        resp.status_code >= 400
        and "Only one NetBox endpoint is allowed" not in resp.text
    ):
        raise AssertionError(
            f"Unable to configure proxbox-api NetBox endpoint: {resp.status_code} {resp.text}"
        )

    # proxmox endpoint (backend database) -> mock service
    proxmox_payload = {
        "name": "mock-proxmox",
        "ip_address": "proxmox-mock",
        "domain": "proxmox-mock",
        "port": 8006,
        "username": "root@pam",
        "token_name": "e2e",
        "token_value": "e2e-secret",
        "verify_ssl": False,
    }
    resp = requests.post(
        f"{proxbox_base_url}/proxmox/endpoints", json=proxmox_payload, timeout=30
    )
    if resp.status_code >= 400 and "already exists" not in resp.text:
        raise AssertionError(
            f"Unable to configure proxbox-api Proxmox endpoint: {resp.status_code} {resp.text}"
        )

    # smoke check that backend can reach NetBox endpoint route itself
    status_resp = requests.get(f"{proxbox_base_url}/netbox/status", timeout=30)
    _assert_ok(status_resp, context="proxbox-api netbox status")


def _ensure_netbox_plugin_endpoints(
    netbox_base_url: str,
    netbox_token: str,
    netbox_token_id: int,
) -> dict[str, int]:
    headers = {
        "Authorization": f"Token {netbox_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    proxmox = _post_json(
        f"{netbox_base_url}/api/plugins/proxbox/endpoints/proxmox/",
        {
            "name": "mock-proxmox",
            "domain": "proxmox-mock",
            "port": 8006,
            "mode": "cluster",
            "username": "root@pam",
            "token_name": "e2e",
            "token_value": "e2e-secret",
            "verify_ssl": False,
        },
        headers,
        context="create plugin Proxmox endpoint",
    )
    netbox_ep = _post_json(
        f"{netbox_base_url}/api/plugins/proxbox/endpoints/netbox/",
        {
            "name": "local-netbox",
            "domain": "netbox",
            "port": 8080,
            "token_version": "v1",
            "token": {"id": netbox_token_id},
            "verify_ssl": False,
        },
        headers,
        context="create plugin NetBox endpoint",
    )
    fastapi = _post_json(
        f"{netbox_base_url}/api/plugins/proxbox/endpoints/fastapi/",
        {
            "name": "local-proxbox-api",
            "domain": "proxbox-api",
            "port": 8000,
            "verify_ssl": False,
            "token": "",
            "use_websocket": False,
            "websocket_domain": "",
            "websocket_port": 8000,
            "server_side_websocket": False,
        },
        headers,
        context="create plugin FastAPI endpoint",
    )

    return {
        "proxmox_pk": int(proxmox["id"]),
        "netbox_pk": int(netbox_ep["id"]),
        "fastapi_pk": int(fastapi["id"]),
    }


def _assert_plugin_routes(
    netbox_base_url: str, netbox_token: str, endpoint_ids: dict[str, int]
) -> None:
    headers = {"Authorization": f"Token {netbox_token}"}
    route_checks = [
        f"{netbox_base_url}/plugins/proxbox/",
        f"{netbox_base_url}/plugins/proxbox/endpoints/proxmox/{endpoint_ids['proxmox_pk']}/",
        f"{netbox_base_url}/plugins/proxbox/endpoints/netbox/{endpoint_ids['netbox_pk']}/",
        f"{netbox_base_url}/plugins/proxbox/endpoints/fastapi/{endpoint_ids['fastapi_pk']}/",
    ]
    for url in route_checks:
        response = requests.get(url, headers=headers, timeout=30, allow_redirects=False)
        if response.status_code >= 400:
            raise AssertionError(
                f"Plugin route failed: {url} -> HTTP {response.status_code}"
            )

    keepalive_checks = [
        f"{netbox_base_url}/plugins/proxbox/keepalive-status/fastapi/{endpoint_ids['fastapi_pk']}/",
        f"{netbox_base_url}/plugins/proxbox/keepalive-status/proxmox/{endpoint_ids['proxmox_pk']}/",
        f"{netbox_base_url}/plugins/proxbox/keepalive-status/netbox/{endpoint_ids['netbox_pk']}/",
    ]
    for url in keepalive_checks:
        response = requests.get(url, headers=headers, timeout=30)
        payload = _assert_ok(response, context=f"keepalive {url}")
        if payload.get("status") != "success":
            raise AssertionError(f"Keepalive failed for {url}: {payload}")

    list_api_checks = [
        f"{netbox_base_url}/api/plugins/proxbox/storage/?limit=1",
        f"{netbox_base_url}/api/plugins/proxbox/backups/?limit=1",
        f"{netbox_base_url}/api/plugins/proxbox/snapshots/?limit=1",
        f"{netbox_base_url}/api/plugins/proxbox/task-history/?limit=1",
    ]
    for url in list_api_checks:
        response = requests.get(url, headers=headers, timeout=30)
        _assert_ok(response, context=f"plugin api {url}")


def _snapshot_proxbox_job_ids(netbox_base_url: str, netbox_token: str) -> set[int]:
    headers = {"Authorization": f"Token {netbox_token}", "Accept": "application/json"}
    jobs_payload = _assert_ok(
        requests.get(
            f"{netbox_base_url}/api/core/jobs/?limit=50", headers=headers, timeout=30
        ),
        context="list existing jobs",
    )
    results = jobs_payload.get("results", [])
    if not isinstance(results, list):
        return set()
    job_ids: set[int] = set()
    for job in results:
        if not isinstance(job, dict):
            continue
        if not str(job.get("name", "")).startswith("Proxbox Sync"):
            continue
        job_id = _extract_id(job.get("id"))
        if job_id is not None:
            job_ids.add(job_id)
    return job_ids


def _trigger_and_wait_sync(
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
    seen_job_ids = _snapshot_proxbox_job_ids(netbox_base_url, netbox_token)

    trigger = requests.post(
        f"{netbox_base_url}{route}",
        headers=headers,
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
        jobs_payload = _assert_ok(jobs_response, context="list jobs")
        results: Iterable[dict] = jobs_payload.get("results", [])
        proxbox_jobs = [
            job
            for job in results
            if str(job.get("name", "")).startswith("Proxbox Sync")
        ]
        for job in proxbox_jobs:
            job_id = _extract_id(job.get("id"))
            if job_id is None or job_id in seen_job_ids:
                continue
            name = str(job.get("name", "")).lower()
            if expected_lower and expected_lower not in name:
                continue
            status = str(job.get("status", "")).lower()
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


def _assert_devices_sync_data(
    netbox_base_url: str, netbox_token: str
) -> dict[str, int]:
    headers = {"Authorization": f"Token {netbox_token}"}

    cluster_types = _list_records(
        f"{netbox_base_url}/api/virtualization/cluster-types/",
        headers,
        context="cluster types",
        params={"slug": "cluster", "limit": 10},
    )
    cluster_type = _require_one(
        cluster_types, label="cluster type", key="slug", value="cluster"
    )

    clusters = _list_records(
        f"{netbox_base_url}/api/virtualization/clusters/",
        headers,
        context="clusters",
        params={"name": "e2e-cluster", "limit": 10},
    )
    cluster = _require_one(clusters, label="cluster", key="name", value="e2e-cluster")
    cluster_type_id = _extract_id(cluster.get("type"))
    if cluster_type_id != _extract_id(cluster_type.get("id")):
        raise AssertionError(
            f"Cluster type mismatch for e2e-cluster: {cluster.get('type')}"
        )

    sites = _list_records(
        f"{netbox_base_url}/api/dcim/sites/",
        headers,
        context="sites",
        params={"name": "Proxmox Default Site - e2e-cluster", "limit": 10},
    )
    site = _require_one(
        sites,
        label="site",
        key="name",
        value="Proxmox Default Site - e2e-cluster",
    )

    manufacturers = _list_records(
        f"{netbox_base_url}/api/dcim/manufacturers/",
        headers,
        context="manufacturers",
        params={"slug": "proxmox", "limit": 10},
    )
    _require_one(
        manufacturers,
        label="manufacturer",
        key="slug",
        value="proxmox",
    )

    device_types = _list_records(
        f"{netbox_base_url}/api/dcim/device-types/",
        headers,
        context="device types",
        params={"model": "Proxmox Generic Device", "limit": 10},
    )
    _require_one(
        device_types,
        label="device type",
        key="model",
        value="Proxmox Generic Device",
    )

    device_roles = _list_records(
        f"{netbox_base_url}/api/dcim/device-roles/",
        headers,
        context="device roles",
        params={"slug": "proxmox-node", "limit": 10},
    )
    _require_one(
        device_roles,
        label="device role",
        key="slug",
        value="proxmox-node",
    )

    devices = _list_records(
        f"{netbox_base_url}/api/dcim/devices/",
        headers,
        context="devices",
        params={"name": "pve01", "limit": 20},
    )
    device = _require_one(devices, label="device", key="name", value="pve01")
    if _extract_id(device.get("cluster")) != _extract_id(cluster.get("id")):
        raise AssertionError("Device pve01 is not linked to e2e-cluster")
    if _extract_id(device.get("site")) != _extract_id(site.get("id")):
        raise AssertionError("Device pve01 is not linked to expected default site")

    return {
        "cluster_id": int(_extract_id(cluster.get("id")) or 0),
        "site_id": int(_extract_id(site.get("id")) or 0),
        "device_id": int(_extract_id(device.get("id")) or 0),
    }


def _assert_storage_sync_data(
    netbox_base_url: str, netbox_token: str, cluster_id: int
) -> None:
    headers = {"Authorization": f"Token {netbox_token}"}
    storage_records = _list_records(
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
        if _extract_id(record.get("cluster")) != cluster_id:
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


def _assert_virtual_machines_sync_data(
    netbox_base_url: str,
    netbox_token: str,
    *,
    cluster_id: int,
    device_id: int,
) -> dict[int, int]:
    vm_101 = _get_vm_by_proxmox_vmid(netbox_base_url, netbox_token, 101)
    vm_102 = _get_vm_by_proxmox_vmid(netbox_base_url, netbox_token, 102)

    if _extract_status_value(vm_101.get("status")) != "active":
        raise AssertionError(
            f"Expected VM 101 status active, got {vm_101.get('status')}"
        )
    if _extract_status_value(vm_102.get("status")) != "active":
        raise AssertionError(
            f"Expected VM 102 status active, got {vm_102.get('status')}"
        )

    for vm in (vm_101, vm_102):
        if _extract_id(vm.get("cluster")) != cluster_id:
            raise AssertionError(
                f"VM {vm.get('name')} is not linked to expected cluster"
            )
        if _extract_id(vm.get("device")) != device_id:
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
        101: int(_extract_id(vm_101.get("id")) or 0),
        102: int(_extract_id(vm_102.get("id")) or 0),
    }


def _assert_virtual_disks_sync_data(
    netbox_base_url: str,
    netbox_token: str,
    *,
    vm_ids_by_vmid: dict[int, int],
) -> None:
    headers = {"Authorization": f"Token {netbox_token}"}
    disks = _list_records(
        f"{netbox_base_url}/api/virtualization/virtual-disks/",
        headers,
        context="virtual disks",
        params={"limit": 200},
    )
    if len(disks) < 2:
        raise AssertionError(f"Expected at least 2 virtual disks, got {len(disks)}")

    disk_vm_ids = {
        _extract_id(disk.get("virtual_machine"))
        for disk in disks
        if _extract_id(disk.get("virtual_machine")) is not None
    }
    for vmid, vm_id in vm_ids_by_vmid.items():
        if vm_id not in disk_vm_ids:
            raise AssertionError(
                f"No virtual disks found for VM vmid={vmid} id={vm_id}"
            )


def _assert_backups_sync_data(
    netbox_base_url: str,
    netbox_token: str,
    *,
    vm_ids_by_vmid: dict[int, int],
) -> None:
    headers = {"Authorization": f"Token {netbox_token}"}
    backups = _list_records(
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
        record = _require_one(backups, label="backup", key="volume_id", value=volume_id)
        if int(record.get("vmid") or -1) != vmid:
            raise AssertionError(
                f"Backup {volume_id} has vmid={record.get('vmid')} expected={vmid}"
            )
        if _extract_id(record.get("virtual_machine")) != vm_ids_by_vmid[vmid]:
            raise AssertionError(
                f"Backup {volume_id} linked to unexpected virtual_machine={record.get('virtual_machine')}"
            )
        if _extract_id(record.get("proxmox_storage")) is None:
            raise AssertionError(f"Backup {volume_id} missing proxmox_storage relation")


def _assert_snapshots_sync_data(
    netbox_base_url: str,
    netbox_token: str,
    *,
    vm_ids_by_vmid: dict[int, int],
) -> None:
    headers = {"Authorization": f"Token {netbox_token}"}
    snapshots = _list_records(
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
        if _extract_id(record.get("virtual_machine")) != vm_ids_by_vmid[vmid]:
            raise AssertionError(
                f"Snapshot relation mismatch for vmid={vmid}: {record}"
            )
        status = _extract_status_value(record.get("status"))
        if status != "active":
            raise AssertionError(
                f"Expected active snapshot status for vmid={vmid}, got {status}"
            )
        seen.add(key)

    missing = expected_snapshots - seen
    if missing:
        raise AssertionError(f"Missing expected snapshots: {sorted(missing)}")


def _assert_task_history_sync_data(
    netbox_base_url: str,
    netbox_token: str,
    *,
    vm_id_101: int,
) -> None:
    headers = {"Authorization": f"Token {netbox_token}"}
    records = _list_records(
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
        if _extract_id(record.get("virtual_machine")) == vm_id_101:
            linked_to_vm_101 = True

    if not linked_to_vm_101:
        raise AssertionError("Expected at least one task history linked to VM 101")
    headers = {"Authorization": f"Token {netbox_token}"}
    checks = [
        ("storage", f"{netbox_base_url}/api/plugins/proxbox/storage/?limit=1"),
        ("backups", f"{netbox_base_url}/api/plugins/proxbox/backups/?limit=1"),
        ("snapshots", f"{netbox_base_url}/api/plugins/proxbox/snapshots/?limit=1"),
    ]
    for label, url in checks:
        payload = _assert_ok(
            requests.get(url, headers=headers, timeout=30), context=label
        )
        count = int(payload.get("count", 0))
        if count < 1:
            raise AssertionError(f"Expected synced {label} records, got count={count}")


def _extract_status_value(raw_status) -> str:
    if isinstance(raw_status, dict):
        value = raw_status.get("value")
        if value:
            return str(value).strip().lower()
        label = raw_status.get("label")
        if label:
            return str(label).strip().lower()
    return str(raw_status or "").strip().lower()


def _get_vm_by_proxmox_vmid(netbox_base_url: str, netbox_token: str, vmid: int) -> dict:
    headers = {"Authorization": f"Token {netbox_token}"}
    response = requests.get(
        f"{netbox_base_url}/api/virtualization/virtual-machines/",
        headers=headers,
        params={"cf_proxmox_vm_id": vmid, "limit": 5},
        timeout=30,
    )
    payload = _assert_ok(response, context=f"lookup vm cf_proxmox_vm_id={vmid}")
    results = payload.get("results", [])
    if not isinstance(results, list) or not results:
        raise AssertionError(f"No NetBox VM found with cf_proxmox_vm_id={vmid}")
    return results[0]


def _set_mock_vm_status(mock_base_url: str, vmid: int, status: str) -> None:
    response = requests.post(
        f"{mock_base_url}/__admin/vm/{vmid}/status",
        json={"status": status},
        timeout=15,
    )
    payload = _assert_ok(response, context=f"set proxmox mock vm status vmid={vmid}")
    if payload.get("ok") is not True:
        raise AssertionError(f"Failed updating proxmox mock VM status: {payload}")


def _assert_vm_status_transition(
    netbox_base_url: str, netbox_token: str, proxmox_mock_base_url: str
) -> None:
    vm = _get_vm_by_proxmox_vmid(netbox_base_url, netbox_token, 101)
    initial_status = _extract_status_value(vm.get("status"))
    if initial_status != "active":
        raise AssertionError(
            f"Expected initial VM status active for vmid=101, got {initial_status!r}"
        )

    _set_mock_vm_status(proxmox_mock_base_url, 101, "stopped")
    _trigger_and_wait_sync(
        netbox_base_url,
        netbox_token,
        route="/plugins/proxbox/sync/full-update/",
        expected_name_fragment="full update",
    )

    updated_vm = _get_vm_by_proxmox_vmid(netbox_base_url, netbox_token, 101)
    updated_status = _extract_status_value(updated_vm.get("status"))
    if updated_status != "offline":
        raise AssertionError(
            f"Expected updated VM status offline for vmid=101, got {updated_status!r}"
        )


def _assert_backend_stream(proxbox_base_url: str) -> dict[str, Any]:
    complete_payload: dict | None = None
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


def _run_and_assert_all_sync_operations(
    netbox_base_url: str,
    netbox_token: str,
    proxmox_mock_base_url: str,
) -> None:
    _trigger_and_wait_sync(
        netbox_base_url,
        netbox_token,
        route="/plugins/proxbox/sync/devices/",
        expected_name_fragment="devices",
    )
    device_refs = _assert_devices_sync_data(netbox_base_url, netbox_token)

    _trigger_and_wait_sync(
        netbox_base_url,
        netbox_token,
        route="/plugins/proxbox/sync/storage/",
        expected_name_fragment="storage",
    )
    _assert_storage_sync_data(
        netbox_base_url,
        netbox_token,
        cluster_id=device_refs["cluster_id"],
    )

    _trigger_and_wait_sync(
        netbox_base_url,
        netbox_token,
        route="/plugins/proxbox/sync/virtual-machines/",
        expected_name_fragment="virtual machines",
    )
    vm_ids_by_vmid = _assert_virtual_machines_sync_data(
        netbox_base_url,
        netbox_token,
        cluster_id=device_refs["cluster_id"],
        device_id=device_refs["device_id"],
    )

    _trigger_and_wait_sync(
        netbox_base_url,
        netbox_token,
        route="/plugins/proxbox/sync/virtual-machines/virtual-disks/",
        expected_name_fragment="virtual disks",
    )
    _assert_virtual_disks_sync_data(
        netbox_base_url,
        netbox_token,
        vm_ids_by_vmid=vm_ids_by_vmid,
    )

    _trigger_and_wait_sync(
        netbox_base_url,
        netbox_token,
        route="/plugins/proxbox/sync/virtual-machines/backups/",
        expected_name_fragment="vm backups",
    )
    _assert_backups_sync_data(
        netbox_base_url,
        netbox_token,
        vm_ids_by_vmid=vm_ids_by_vmid,
    )

    _trigger_and_wait_sync(
        netbox_base_url,
        netbox_token,
        route="/plugins/proxbox/sync/virtual-machines/snapshots/",
        expected_name_fragment="vm snapshots",
    )
    _assert_snapshots_sync_data(
        netbox_base_url,
        netbox_token,
        vm_ids_by_vmid=vm_ids_by_vmid,
    )

    _trigger_and_wait_sync(
        netbox_base_url,
        netbox_token,
        route="/plugins/proxbox/sync/full-update/",
        expected_name_fragment="full update",
    )
    _assert_vm_status_transition(netbox_base_url, netbox_token, proxmox_mock_base_url)


def main() -> None:
    netbox_base_url = _must_getenv("NETBOX_BASE_URL")
    proxbox_base_url = _must_getenv("PROXBOX_BASE_URL")
    proxmox_mock_base_url = _must_getenv("PROXMOX_MOCK_BASE_URL")
    netbox_public_url = _must_getenv("NETBOX_PUBLIC_URL")
    netbox_token = _must_getenv("NETBOX_API_TOKEN")
    netbox_token_id = int(_must_getenv("NETBOX_TOKEN_ID"))

    _wait_http_ok(f"{netbox_base_url}/api/")
    _wait_http_ok(f"{proxbox_base_url}/")

    _ensure_proxbox_backend_endpoints(proxbox_base_url, netbox_public_url, netbox_token)
    endpoint_ids = _ensure_netbox_plugin_endpoints(
        netbox_base_url, netbox_token, netbox_token_id
    )
    _assert_plugin_routes(netbox_base_url, netbox_token, endpoint_ids)
    _run_and_assert_all_sync_operations(
        netbox_base_url,
        netbox_token,
        proxmox_mock_base_url,
    )
    _assert_backend_stream(proxbox_base_url)
    vm_101 = _get_vm_by_proxmox_vmid(netbox_base_url, netbox_token, 101)
    vm_101_id = int(_extract_id(vm_101.get("id")) or 0)
    if vm_101_id < 1:
        raise AssertionError("Unable to resolve NetBox VM id for vmid=101")
    _assert_task_history_sync_data(
        netbox_base_url,
        netbox_token,
        vm_id_101=vm_101_id,
    )
    print("E2E stack test succeeded")


if __name__ == "__main__":
    main()
