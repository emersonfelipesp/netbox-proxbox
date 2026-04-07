"""Tests for e2e_stack_check."""

from __future__ import annotations

from stack_common import extract_id, get_vm_by_proxmox_vmid, must_getenv, wait_http_ok
from stack_setup import (
    assert_plugin_routes,
    ensure_netbox_plugin_endpoints,
    ensure_proxbox_backend_endpoints,
)
from stack_sync import (
    assert_backend_stream,
    assert_task_history_sync_data,
    run_and_assert_all_sync_operations,
)


def main() -> None:
    netbox_base_url = must_getenv("NETBOX_BASE_URL")
    proxbox_base_url = must_getenv("PROXBOX_BASE_URL")
    proxmox_mock_base_url = must_getenv("PROXMOX_MOCK_BASE_URL")
    netbox_public_url = must_getenv("NETBOX_PUBLIC_URL")
    netbox_token = must_getenv("NETBOX_API_TOKEN")
    netbox_token_id = int(must_getenv("NETBOX_TOKEN_ID"))

    wait_http_ok(f"{netbox_base_url}/api/")
    wait_http_ok(f"{proxbox_base_url}/")

    ensure_proxbox_backend_endpoints(proxbox_base_url, netbox_public_url, netbox_token)
    endpoint_ids = ensure_netbox_plugin_endpoints(
        netbox_base_url,
        netbox_token,
        netbox_token_id,
        netbox_public_url=netbox_public_url,
    )
    assert_plugin_routes(netbox_base_url, netbox_token, endpoint_ids)
    run_and_assert_all_sync_operations(
        netbox_base_url,
        netbox_token,
        proxmox_mock_base_url,
    )
    assert_backend_stream(proxbox_base_url)

    vm_101 = get_vm_by_proxmox_vmid(netbox_base_url, netbox_token, 101)
    vm_101_id = int(extract_id(vm_101.get("id")) or 0)
    if vm_101_id < 1:
        raise AssertionError("Unable to resolve NetBox VM id for vmid=101")
    assert_task_history_sync_data(
        netbox_base_url,
        netbox_token,
        vm_id_101=vm_101_id,
    )

    print("E2E stack test succeeded")


if __name__ == "__main__":
    main()
