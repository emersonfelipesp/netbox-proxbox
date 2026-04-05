from __future__ import annotations

import os
import requests
from urllib.parse import urlparse

from stack_common import assert_ok, post_json


def ensure_proxbox_backend_endpoints(
    proxbox_base_url: str,
    netbox_public_url: str,
    netbox_token: str,
) -> None:
    parsed_netbox = urlparse(netbox_public_url)
    netbox_host = parsed_netbox.hostname
    netbox_port = parsed_netbox.port or 8080

    print(f"Configuring NetBox endpoint: host={netbox_host}, port={netbox_port}")
    netbox_payload = {
        "name": "netbox",
        "ip_address": netbox_host,
        "domain": netbox_host,
        "port": netbox_port,
        "token_version": "v1",
        "token": netbox_token,
        "verify_ssl": False,
    }
    resp = requests.post(
        f"{proxbox_base_url}/netbox/endpoint", json=netbox_payload, timeout=30
    )
    print(f"NetBox endpoint response: HTTP {resp.status_code} - {resp.text[:300]}")
    if (
        resp.status_code >= 400
        and "Only one NetBox endpoint is allowed" not in resp.text
    ):
        raise AssertionError(
            f"Unable to configure proxbox-api NetBox endpoint: {resp.status_code} {resp.text}"
        )

    print("Checking NetBox status on proxbox-api backend")
    status_resp = requests.get(f"{proxbox_base_url}/netbox/status", timeout=30)
    print(
        f"NetBox status response: HTTP {status_resp.status_code} - {status_resp.text[:300]}"
    )
    assert_ok(status_resp, context="proxbox-api netbox status")

    # Do not seed a standalone Proxmox endpoint directly into proxbox-api here.
    # The NetBox plugin keepalive path synchronizes the NetBox-managed Proxmox
    # endpoint into the backend, and creating another backend-only record here
    # causes the same Proxmox host to be synced twice in E2E.


def ensure_netbox_plugin_endpoints(
    netbox_base_url: str,
    netbox_token: str,
    netbox_token_id: int,
    netbox_public_url: str = "",
) -> dict[str, int]:
    headers = {
        "Authorization": f"Token {netbox_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    parsed_netbox = urlparse(netbox_public_url) if netbox_public_url else None
    netbox_host = (parsed_netbox.hostname if parsed_netbox else None) or "netbox"
    netbox_port = (parsed_netbox.port if parsed_netbox else None) or 8080

    proxmox_ip = os.environ.get("PROXMOX_MOCK_IP", "127.0.0.1")
    proxbox_api_ip = os.environ.get("PROXBOX_API_IP", "127.0.0.1")

    # ip_address fields are FKs to ipam.IPAddress — create the IPAM records first
    netbox_ip_obj = post_json(
        f"{netbox_base_url}/api/ipam/ip-addresses/",
        {"address": f"{netbox_host}/32"},
        headers,
        context="create NetBox IPAddress in IPAM",
    )
    proxmox_ip_obj = post_json(
        f"{netbox_base_url}/api/ipam/ip-addresses/",
        {"address": f"{proxmox_ip}/32"},
        headers,
        context="create Proxmox mock IPAddress in IPAM",
    )
    proxbox_api_ip_obj = post_json(
        f"{netbox_base_url}/api/ipam/ip-addresses/",
        {"address": f"{proxbox_api_ip}/32"},
        headers,
        context="create ProxBox API IPAddress in IPAM",
    )

    proxmox = post_json(
        f"{netbox_base_url}/api/plugins/proxbox/endpoints/proxmox/",
        {
            "name": "mock-proxmox",
            "ip_address": proxmox_ip_obj["id"],
            "port": 8000,
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
            "ip_address": netbox_ip_obj["id"],
            "port": netbox_port,
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
            "ip_address": proxbox_api_ip_obj["id"],
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
        print(f"Checking keepalive: {url}")
        response = requests.get(url, headers=headers, timeout=30)
        print(
            f"Keepalive response: HTTP {response.status_code} - {response.text[:500]}"
        )
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
