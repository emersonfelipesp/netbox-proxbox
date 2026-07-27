"""Tests for e2e_stack_check."""

from __future__ import annotations

from stack_common import (
    extract_id,
    get_vm_by_proxmox_vmid,
    load_stack_context,
    log_service_skip,
    wait_http_ok,
)
from stack_setup import (
    assert_backend_key_rotation_contract,
    assert_plugin_internal_contracts,
    assert_plugin_routes,
    assert_proxmox_mock_contract,
    create_proxbox_custom_fields,
    ensure_netbox_plugin_endpoints,
    ensure_proxbox_backend_endpoints,
    register_proxbox_api_key,
)
from stack_sync import (
    assert_backend_stream,
    assert_task_history_sync_data,
    run_and_assert_all_sync_operations,
)


def main() -> None:
    stack = load_stack_context()
    print(f"Running E2E stack checks for service={stack.service}")

    wait_http_ok(f"{stack.netbox_base_url}/api/")
    wait_http_ok(f"{stack.proxbox_base_url}/")
    wait_http_ok(f"{stack.proxmox_mock_base_url}/health", verify=False)
    assert_proxmox_mock_contract(stack.proxmox_mock_base_url, stack.service)

    proxbox_api_key = register_proxbox_api_key(stack.proxbox_base_url)
    ensure_proxbox_backend_endpoints(
        stack.proxbox_base_url,
        stack.netbox_public_url,
        stack.netbox_token,
        proxbox_api_key=proxbox_api_key,
    )
    endpoint_ids = ensure_netbox_plugin_endpoints(
        stack.netbox_base_url,
        stack.netbox_token,
        stack.netbox_token_id,
        netbox_public_url=stack.netbox_public_url,
        proxbox_api_key=proxbox_api_key,
    )
    proxbox_api_key = assert_backend_key_rotation_contract(
        stack.proxbox_base_url,
        stack.netbox_base_url,
        stack.netbox_token,
        endpoint_ids["fastapi_pk"],
        proxbox_api_key,
    )
    assert_plugin_routes(
        stack.netbox_base_url,
        stack.netbox_token,
        endpoint_ids,
        service=stack.service,
    )
    assert_plugin_internal_contracts(
        stack.netbox_base_url,
        stack.netbox_token,
        endpoint_ids,
    )
    create_proxbox_custom_fields(
        stack.proxbox_base_url, proxbox_api_key=proxbox_api_key
    )
    run_and_assert_all_sync_operations(
        stack.netbox_base_url,
        stack.netbox_token,
        stack.proxmox_mock_base_url,
        service=stack.service,
    )
    assert_backend_stream(
        stack.proxbox_base_url,
        proxbox_api_key=proxbox_api_key,
        service=stack.service,
    )

    if stack.service != "pve":
        log_service_skip(stack.service, "NetBox VM lookup for vmid=101")
        assert_task_history_sync_data(
            stack.netbox_base_url,
            stack.netbox_token,
            vm_id_101=0,
            service=stack.service,
        )
        print(f"E2E stack test succeeded for service={stack.service}")
        return

    vm_101 = get_vm_by_proxmox_vmid(stack.netbox_base_url, stack.netbox_token, 101)
    vm_101_id = int(extract_id(vm_101.get("id")) or 0)
    if vm_101_id < 1:
        raise AssertionError("Unable to resolve NetBox VM id for vmid=101")
    assert_task_history_sync_data(
        stack.netbox_base_url,
        stack.netbox_token,
        vm_id_101=vm_101_id,
        service=stack.service,
    )

    print(f"E2E stack test succeeded for service={stack.service}")


if __name__ == "__main__":
    main()
