"""Tests for stack_common."""

from __future__ import annotations

import json
import os
import time
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
        raise RuntimeError(
            f"Invalid PROXMOX_SERVICE={service!r}; expected one of: {valid}"
        )
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


def wait_http_ok(url: str, *, timeout_seconds: int = 300, verify: bool = True) -> None:
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


def assert_ok(
    response: requests.Response,
    *,
    context: str,
    include_response_body: bool = True,
) -> dict:
    if response.status_code >= 400:
        detail = f" - {response.text}" if include_response_body else ""
        raise AssertionError(f"{context} failed: HTTP {response.status_code}{detail}")
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


def _remaining_request_timeout(context: str, deadline: float | None) -> float:
    """Return a request timeout bounded by an optional absolute deadline."""
    if deadline is None:
        return 30.0
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise AssertionError(f"{context} exceeded its wall-clock deadline")
    return min(30.0, remaining)


def read_json_with_deadline(
    url: str,
    headers: dict,
    *,
    context: str,
    deadline: float | None,
) -> dict[str, Any]:
    """Read one non-redirected JSON page within the absolute deadline."""
    response = requests.get(
        url,
        headers=headers,
        timeout=_remaining_request_timeout(context, deadline),
        allow_redirects=False,
        stream=True,
    )
    try:
        if 300 <= response.status_code < 400:
            raise AssertionError(
                f"{context} failed: HTTP {response.status_code} redirect rejected"
            )
        if response.status_code >= 400:
            raise AssertionError(f"{context} failed: HTTP {response.status_code}")
        body = bytearray()
        for chunk in response.iter_content(chunk_size=64 * 1024):
            if deadline is not None and time.monotonic() >= deadline:
                raise AssertionError(f"{context} exceeded its wall-clock deadline")
            body.extend(chunk)
        try:
            payload = json.loads(body)
        except (TypeError, ValueError) as error:
            raise AssertionError(f"{context} did not return JSON: {error}") from error
        if not isinstance(payload, dict):
            raise AssertionError(f"{context} did not return a JSON object")
        return payload
    finally:
        response.close()


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


def _positive_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        return None
    return value


def _nested_positive_id(value: Any) -> int | None:
    if not isinstance(value, dict):
        return None
    return _positive_int(value.get("id"))


def _complete_sync_state_results(payload: Any, vmid: int) -> list[Any]:
    if not isinstance(payload, dict) or "results" not in payload:
        raise AssertionError(f"Invalid VM sync-state envelope for proxmox_vm_id={vmid}")
    results = payload["results"]
    if not isinstance(results, list):
        raise AssertionError(f"Invalid VM sync-state results for proxmox_vm_id={vmid}")
    count = payload.get("count")
    if (
        isinstance(count, bool)
        or not isinstance(count, int)
        or count != len(results)
        or payload.get("next") is not None
    ):
        raise AssertionError(
            f"Incomplete VM sync-state page for proxmox_vm_id={vmid}: "
            f"count={count!r}, returned={len(results)}, next={payload.get('next')!r}"
        )
    return results


def _validated_linked_vm_id(record: Any, vmid: int) -> int:
    returned_vmid = record.get("proxmox_vm_id") if isinstance(record, dict) else None
    if _positive_int(returned_vmid) != vmid:
        raise AssertionError(
            f"VM sync-state filter mismatch for proxmox_vm_id={vmid}: "
            f"returned {returned_vmid!r}"
        )
    vm_id = _nested_positive_id(record.get("virtual_machine"))
    if vm_id is None:
        raise AssertionError(
            f"VM sync state proxmox_vm_id={vmid} has no virtual_machine identity"
        )
    return vm_id


def _linked_vm_id(results: list[Any], vmid: int) -> int:
    linked_ids = [_validated_linked_vm_id(record, vmid) for record in results]
    if len(linked_ids) != 1:
        raise AssertionError(
            f"Expected one VM sync state with proxmox_vm_id={vmid}, "
            f"found {len(linked_ids)}"
        )
    return linked_ids[0]


def get_vm_by_proxmox_vmid(netbox_base_url: str, netbox_token: str, vmid: int) -> dict:
    validated_vmid = _positive_int(vmid)
    if validated_vmid is None:
        raise AssertionError(f"Invalid requested proxmox_vm_id={vmid!r}")
    headers = {"Authorization": f"Token {netbox_token}"}
    response = requests.get(
        f"{netbox_base_url}/api/plugins/proxbox/sync-state/virtual-machines/",
        headers=headers,
        params={"proxmox_vm_id": validated_vmid, "limit": 100},
        timeout=30,
    )
    payload = assert_ok(
        response,
        context=f"lookup vm sync state proxmox_vm_id={validated_vmid}",
    )
    vm_id = _linked_vm_id(
        _complete_sync_state_results(payload, validated_vmid), validated_vmid
    )
    vm_response = requests.get(
        f"{netbox_base_url}/api/virtualization/virtual-machines/{vm_id}/",
        headers=headers,
        timeout=30,
    )
    vm = assert_ok(
        vm_response,
        context=f"lookup NetBox VM {vm_id} for vmid={validated_vmid}",
    )
    detail_id = _positive_int(vm.get("id") if isinstance(vm, dict) else None)
    if detail_id != vm_id:
        raise AssertionError(
            f"NetBox VM detail identity mismatch for vmid={validated_vmid}: "
            f"expected {vm_id}, returned {detail_id!r}"
        )
    return vm
