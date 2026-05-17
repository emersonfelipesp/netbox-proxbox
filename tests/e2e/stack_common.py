"""Tests for stack_common."""

from __future__ import annotations

import os
import time
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

import requests

VALID_PROXMOX_SERVICES = ("pve", "pbs", "pdm")


@dataclass(frozen=True)
class StackContext:
    netbox_base_url: str
    proxbox_base_url: str
    proxmox_mock_base_url: str
    netbox_public_url: str
    netbox_token: str
    netbox_token_id: int
    service: str


def must_getenv(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def get_proxmox_service() -> str:
    service = (os.getenv("PROXMOX_SERVICE") or "pve").strip().lower()
    if service not in VALID_PROXMOX_SERVICES:
        valid = ", ".join(VALID_PROXMOX_SERVICES)
        raise RuntimeError(f"Invalid PROXMOX_SERVICE={service!r}; expected one of: {valid}")
    return service


def load_stack_context() -> StackContext:
    return StackContext(
        netbox_base_url=must_getenv("NETBOX_BASE_URL"),
        proxbox_base_url=must_getenv("PROXBOX_BASE_URL"),
        proxmox_mock_base_url=must_getenv("PROXMOX_MOCK_BASE_URL"),
        netbox_public_url=must_getenv("NETBOX_PUBLIC_URL"),
        netbox_token=must_getenv("NETBOX_API_TOKEN"),
        netbox_token_id=int(must_getenv("NETBOX_TOKEN_ID")),
        service=get_proxmox_service(),
    )


def log_service_skip(service: str, name: str) -> None:
    print(f"service={service}: skipping {name}")


def wait_http_ok(
    url: str, *, timeout_seconds: int = 300, verify: bool = True
) -> None:
    deadline = time.time() + timeout_seconds
    last_error = ""
    while time.time() < deadline:
        try:
            response = requests.get(url, timeout=5, verify=verify)
            if response.status_code < 500:
                return
            last_error = f"HTTP {response.status_code}"
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
        time.sleep(2)
    raise RuntimeError(f"Timed out waiting for {url}: {last_error}")


def assert_ok(response: requests.Response, *, context: str) -> dict:
    if response.status_code >= 400:
        raise AssertionError(
            f"{context} failed: HTTP {response.status_code} - {response.text}"
        )
    try:
        return response.json()
    except Exception as exc:  # noqa: BLE001
        raise AssertionError(f"{context} did not return JSON: {exc}") from exc


def extract_id(value: Any) -> int | None:
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


def extract_status_value(raw_status: Any) -> str:
    if isinstance(raw_status, dict):
        value = raw_status.get("value")
        if value:
            return str(value).strip().lower()
        label = raw_status.get("label")
        if label:
            return str(label).strip().lower()
    return str(raw_status or "").strip().lower()


def list_records(
    url: str,
    headers: dict,
    *,
    context: str,
    params: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    response = requests.get(url, headers=headers, params=params, timeout=30)
    payload = assert_ok(response, context=context)
    results = payload.get("results")
    if not isinstance(results, list):
        raise AssertionError(f"{context} response missing results[]: {payload}")
    return [record for record in results if isinstance(record, dict)]


def require_one(
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


def post_json(url: str, payload: dict, headers: dict, *, context: str) -> dict:
    response = requests.post(url, json=payload, headers=headers, timeout=30)
    return assert_ok(response, context=context)


def get_vm_by_proxmox_vmid(netbox_base_url: str, netbox_token: str, vmid: int) -> dict:
    headers = {"Authorization": f"Token {netbox_token}"}
    response = requests.get(
        f"{netbox_base_url}/api/virtualization/virtual-machines/",
        headers=headers,
        params={"cf_proxmox_vm_id": vmid, "limit": 5},
        timeout=30,
    )
    payload = assert_ok(response, context=f"lookup vm cf_proxmox_vm_id={vmid}")
    results = payload.get("results", [])
    if not isinstance(results, list) or not results:
        raise AssertionError(f"No NetBox VM found with cf_proxmox_vm_id={vmid}")
    return results[0]


def snapshot_proxbox_job_ids(netbox_base_url: str, netbox_token: str) -> set[int]:
    headers = {"Authorization": f"Token {netbox_token}", "Accept": "application/json"}
    jobs_payload = assert_ok(
        requests.get(
            f"{netbox_base_url}/api/core/jobs/?limit=50", headers=headers, timeout=30
        ),
        context="list existing jobs",
    )
    results: Iterable[dict[str, Any]] = jobs_payload.get("results", [])
    job_ids: set[int] = set()
    for job in results:
        if not isinstance(job, dict):
            continue
        if not str(job.get("name", "")).startswith("Proxbox Sync"):
            continue
        job_id = extract_id(job.get("id"))
        if job_id is not None:
            job_ids.add(job_id)
    return job_ids
