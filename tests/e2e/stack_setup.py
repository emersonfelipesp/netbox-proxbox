from __future__ import annotations

import requests

from stack_common import assert_ok, post_json


def ensure_proxbox_backend_endpoints(
    proxbox_base_url: str,
    netbox_public_url: str,
    netbox_token: str,
) -> None:
    _ = netbox_public_url

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

    status_resp = requests.get(f"{proxbox_base_url}/netbox/status", timeout=30)
    assert_ok(status_resp, context="proxbox-api netbox status")


def ensure_netbox_plugin_endpoints(
    netbox_base_url: str,
    netbox_token: str,
    netbox_token_id: int,
) -> dict[str, int]:
    headers = {
        "Authorization": f"Token {netbox_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    proxmox = post_json(
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
    netbox_ep = post_json(
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
    fastapi = post_json(
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


def assert_plugin_routes(
    netbox_base_url: str,
    netbox_token: str,
    endpoint_ids: dict[str, int],
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
        payload = assert_ok(response, context=f"keepalive {url}")
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
        assert_ok(response, context=f"plugin api {url}")
