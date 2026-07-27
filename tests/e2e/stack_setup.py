"""Tests for stack_setup."""

from __future__ import annotations

import os
import subprocess
from typing import Any
from urllib.parse import urlparse

import requests

from stack_common import assert_ok, list_records, log_service_skip, post_json

# Fixed E2E API key registered with proxbox-api before any management calls.
_E2E_PROXBOX_API_KEY = "proxbox-e2e-api-key-for-e2e-testing"


def assert_proxmox_mock_contract(proxmox_mock_base_url: str, service: str) -> None:
    print(f"Checking Proxmox mock health for service={service}")
    try:
        health = requests.get(
            f"{proxmox_mock_base_url}/health", timeout=15, verify=False
        )
    except requests.exceptions.RequestException as exc:
        raise AssertionError(f"Proxmox mock health probe failed: {exc}") from exc
    if health.status_code >= 400:
        raise AssertionError(
            f"Proxmox mock health failed: HTTP {health.status_code} {health.text[:300]}"
        )

    try:
        version = requests.get(
            f"{proxmox_mock_base_url}/api2/json/version", timeout=15, verify=False
        )
    except requests.exceptions.RequestException as exc:
        raise AssertionError(f"Proxmox mock version probe failed: {exc}") from exc

    if service == "pve":
        payload = assert_ok(version, context="proxmox mock pve version")
        if not isinstance(payload.get("data"), dict):
            raise AssertionError(
                f"PVE mock version payload missing data object: {payload}"
            )
        return

    if version.status_code >= 500:
        raise AssertionError(
            f"{service} mock schema probe failed with server error: "
            f"HTTP {version.status_code} {version.text[:300]}"
        )
    if version.status_code >= 400:
        print(
            f"service={service}: accepted mock schema probe HTTP "
            f"{version.status_code} (no schema yet)"
        )
        return

    try:
        version.json()
    except ValueError as exc:
        raise AssertionError(
            f"{service} mock schema probe returned non-JSON success: {version.text[:300]}"
        ) from exc


def _assert_status_shape(payload: dict[str, Any], *, context: str) -> None:
    required = {
        "status",
        "target_address",
        "target_port",
        "authentication",
        "api_access",
    }
    missing = sorted(required - set(payload))
    if missing:
        raise AssertionError(f"{context} payload missing keys {missing}: {payload}")


def assert_tag_bootstrap(netbox_base_url: str, netbox_token: str) -> None:
    headers = {"Authorization": f"Token {netbox_token}"}
    expected_slugs = (
        "proxbox",
        "proxbox-discovered-qemu",
        "proxbox-discovered-lxc",
        "proxbox-discovered-cluster",
        "proxbox-discovered-node",
    )
    for slug in expected_slugs:
        records = list_records(
            f"{netbox_base_url}/api/extras/tags/",
            headers,
            context=f"tag bootstrap {slug}",
            params={"slug": slug, "limit": 2},
        )
        if not records:
            raise AssertionError(f"Missing bootstrapped tag slug={slug!r}")


def assert_endpoint_singletons(
    netbox_base_url: str,
    netbox_token: str,
    endpoint_ids: dict[str, int],
) -> None:
    headers = {"Authorization": f"Token {netbox_token}"}
    checks = (
        ("NetBoxEndpoint", "netbox", "netbox_pk"),
        ("FastAPIEndpoint", "fastapi", "fastapi_pk"),
    )
    for label, route, id_key in checks:
        records = list_records(
            f"{netbox_base_url}/api/plugins/proxbox/endpoints/{route}/",
            headers,
            context=f"{label} singleton",
            params={"limit": 50},
        )
        if len(records) != 1:
            raise AssertionError(f"Expected one {label}, found {len(records)}")
        if int(records[0].get("id") or 0) != endpoint_ids[id_key]:
            raise AssertionError(f"{label} singleton id mismatch: {records[0]}")


def assert_discovery_api_contracts(netbox_base_url: str, netbox_token: str) -> None:
    headers = {"Authorization": f"Token {netbox_token}"}
    root_payload = assert_ok(
        requests.get(
            f"{netbox_base_url}/api/plugins/proxbox/", headers=headers, timeout=30
        ),
        context="plugin api root",
    )
    for key in ("endpoints", "settings", "resources", "schedule_sync"):
        if key not in root_payload:
            raise AssertionError(f"Plugin API root missing {key!r}: {root_payload}")

    endpoints_payload = assert_ok(
        requests.get(
            f"{netbox_base_url}/api/plugins/proxbox/endpoints/",
            headers=headers,
            timeout=30,
        ),
        context="plugin endpoints api root",
    )
    for key in ("proxmox", "netbox", "fastapi"):
        if key not in endpoints_payload:
            raise AssertionError(
                f"Plugin endpoints API root missing {key!r}: {endpoints_payload}"
            )

    discovery_routes = (
        "resources/clusters",
        "resources/nodes",
        "resources/virtual-machines",
        "resources/lxc-containers",
        "resources/interfaces",
        "resources/ip-addresses",
        "resources/virtual-disks",
    )
    for route in discovery_routes:
        payload = assert_ok(
            requests.get(
                f"{netbox_base_url}/api/plugins/proxbox/{route}/",
                headers=headers,
                timeout=30,
            ),
            context=f"plugin discovery {route}",
        )
        if not isinstance(payload, dict):
            raise AssertionError(
                f"Discovery route {route} returned non-object: {payload}"
            )


def assert_settings_endpoint_reachable(netbox_base_url: str, netbox_token: str) -> None:
    headers = {"Authorization": f"Token {netbox_token}"}
    payload = assert_ok(
        requests.get(
            f"{netbox_base_url}/api/plugins/proxbox/settings/runtime/",
            headers=headers,
            timeout=30,
        ),
        context="plugin settings runtime",
    )
    for key in ("bulk_batch_size", "netbox_timeout", "encryption_key_configured"):
        if key not in payload:
            raise AssertionError(f"Settings runtime payload missing {key!r}: {payload}")


def assert_rq_default_queue_contract() -> None:
    script = (
        "from netbox.constants import RQ_QUEUE_DEFAULT; "
        "from netbox_proxbox.jobs import PROXBOX_SYNC_QUEUE_NAME; "
        "print(f'{PROXBOX_SYNC_QUEUE_NAME}:{RQ_QUEUE_DEFAULT}')"
    )
    cmd = [
        "docker",
        "exec",
        "netbox-e2e",
        "/opt/netbox/venv/bin/python",
        "/opt/netbox/netbox/manage.py",
        "shell",
        "-c",
        script,
    ]
    try:
        result = subprocess.run(
            cmd, check=True, capture_output=True, text=True, timeout=60
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise AssertionError(
            f"Unable to inspect NetBox RQ queue contract: {exc}"
        ) from exc

    output_lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if not output_lines:
        raise AssertionError("RQ queue contract check returned no output")
    queue_name, default_queue = output_lines[-1].split(":", 1)
    if queue_name != default_queue or queue_name != "default":
        raise AssertionError(
            f"Expected PROXBOX_SYNC_QUEUE_NAME to equal default, got {output_lines[-1]!r}"
        )


def assert_plugin_internal_contracts(
    netbox_base_url: str,
    netbox_token: str,
    endpoint_ids: dict[str, int],
) -> None:
    assert_discovery_api_contracts(netbox_base_url, netbox_token)
    assert_tag_bootstrap(netbox_base_url, netbox_token)
    assert_endpoint_singletons(netbox_base_url, netbox_token, endpoint_ids)
    assert_settings_endpoint_reachable(netbox_base_url, netbox_token)
    assert_rq_default_queue_contract()


def register_proxbox_api_key(proxbox_base_url: str) -> str:
    """Bootstrap or authenticate the retained E2E key without false success.

    proxbox-api requires an API key registered via POST /auth/register-key before
    any authenticated management endpoints (e.g. /netbox/endpoint) can be called.
    Returns the API key string so callers can include it as X-Proxbox-API-Key.
    """
    api_key = _E2E_PROXBOX_API_KEY
    status_resp = requests.get(
        f"{proxbox_base_url}/auth/bootstrap-status",
        timeout=10,
        allow_redirects=False,
    )
    status_data = assert_ok(status_resp, context="read proxbox-api bootstrap status")
    needs_bootstrap = status_data.get("needs_bootstrap")
    has_db_keys = status_data.get("has_db_keys")
    if (
        not isinstance(needs_bootstrap, bool)
        or not isinstance(has_db_keys, bool)
        or needs_bootstrap is has_db_keys
    ):
        raise AssertionError("proxbox-api returned an inconsistent bootstrap status")

    if not needs_bootstrap:
        auth_response = requests.get(
            f"{proxbox_base_url}/auth/keys",
            headers={"X-Proxbox-API-Key": api_key},
            timeout=10,
            allow_redirects=False,
        )
        assert_ok(
            auth_response,
            context="authenticate retained proxbox-api E2E key",
            include_response_body=False,
        )
        print("proxbox-api E2E key is already authenticated")
        return api_key

    print("Registering proxbox-api API key...")
    resp = requests.post(
        f"{proxbox_base_url}/auth/register-key",
        json={"api_key": api_key, "label": "netbox-proxbox-e2e"},
        timeout=10,
        allow_redirects=False,
    )
    if resp.status_code != 201:
        raise AssertionError(
            f"Failed to register proxbox-api key: HTTP {resp.status_code}"
        )
    print("proxbox-api E2E key bootstrap succeeded")
    return api_key


def assert_backend_key_rotation_contract(
    proxbox_base_url: str,
    netbox_base_url: str,
    netbox_token: str,
    fastapi_endpoint_id: int,
    current_key: str,
) -> str:
    """Exercise proxbox-api's real key routes and the plugin adoption boundary."""
    create_response = requests.post(
        f"{proxbox_base_url}/auth/keys",
        headers={"X-Proxbox-API-Key": current_key},
        timeout=10,
        allow_redirects=False,
    )
    create_payload = assert_ok(
        create_response,
        context="create proxbox-api replacement key",
        include_response_body=False,
    )
    replacement = str(create_payload.get("raw_key") or "").strip()
    if len(replacement) < 32:
        raise AssertionError("proxbox-api did not return a usable one-time key")

    netbox_headers = {
        "Authorization": f"Token {netbox_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    endpoint_url = (
        f"{netbox_base_url}/api/plugins/proxbox/endpoints/fastapi/"
        f"{fastapi_endpoint_id}/"
    )
    adopt_response = requests.patch(
        endpoint_url,
        json={"token": replacement},
        headers=netbox_headers,
        timeout=30,
        allow_redirects=False,
    )
    assert_ok(
        adopt_response,
        context="adopt proxbox-api replacement key",
        include_response_body=False,
    )

    protected_response = requests.get(
        f"{proxbox_base_url}/auth/keys",
        headers={"X-Proxbox-API-Key": replacement},
        timeout=10,
        allow_redirects=False,
    )
    assert_ok(
        protected_response,
        context="verify adopted proxbox-api key",
        include_response_body=False,
    )

    rejected_candidate = "invalid-e2e-candidate-key-do-not-persist-000000"
    reject_response = requests.patch(
        endpoint_url,
        json={"token": rejected_candidate},
        headers=netbox_headers,
        timeout=30,
        allow_redirects=False,
    )
    if reject_response.status_code != 400:
        raise AssertionError(
            "Invalid backend key adoption did not return HTTP 400 "
            f"(got {reject_response.status_code})"
        )
    if (
        rejected_candidate in reject_response.text
        or replacement in reject_response.text
    ):
        raise AssertionError("Backend key validation response disclosed a credential")

    command = [
        "docker",
        "exec",
        "netbox-e2e",
        "/opt/netbox/venv/bin/python",
        "/opt/netbox/netbox/manage.py",
        "proxbox_fix_tokens",
    ]
    result = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if "All FastAPIEndpoint tokens are registered" not in result.stdout:
        raise AssertionError("Stored replacement key failed post-rejection validation")
    if replacement in result.stdout or rejected_candidate in result.stdout:
        raise AssertionError("Key diagnostics disclosed a credential")
    return replacement


def ensure_proxbox_backend_endpoints(
    proxbox_base_url: str,
    netbox_public_url: str,
    netbox_token: str,
    *,
    proxbox_api_key: str = "",
) -> None:
    auth_headers: dict[str, str] = (
        {"X-Proxbox-API-Key": proxbox_api_key} if proxbox_api_key else {}
    )
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
        f"{proxbox_base_url}/netbox/endpoint",
        json=netbox_payload,
        headers=auth_headers,
        timeout=30,
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
    status_resp = requests.get(
        f"{proxbox_base_url}/netbox/status", headers=auth_headers, timeout=30
    )
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
    *,
    proxbox_api_key: str = "",
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
            "token": proxbox_api_key,
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
    *,
    service: str = "pve",
) -> None:
    headers = {"Authorization": f"Token {netbox_token}"}
    route_checks = [
        f"{netbox_base_url}/plugins/proxbox/home/",
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

    # Settings tab smoke check: confirm the page renders and at least one of
    # the 22 overwrite_* form fields is present (regression for issue #343).
    # The settings view is a NetBox ObjectEditView, which only honors session
    # auth — Token auth on a UI route redirects to /login/. Use a Django login
    # session (admin/admin from the e2e-docker workflow superuser env) so the
    # form renders.
    settings_url = (
        f"{netbox_base_url}/plugins/proxbox/endpoints/proxmox/"
        f"{endpoint_ids['proxmox_pk']}/settings/"
    )
    session = requests.Session()
    session.get(f"{netbox_base_url}/login/", timeout=30)
    csrf = session.cookies.get("csrftoken")
    if not csrf:
        raise AssertionError(
            f"Login page did not set csrftoken cookie at {netbox_base_url}/login/"
        )
    login_resp = session.post(
        f"{netbox_base_url}/login/",
        data={
            "username": "admin",
            "password": "admin",
            "csrfmiddlewaretoken": csrf,
            "next": "/",
        },
        headers={"Referer": f"{netbox_base_url}/login/"},
        allow_redirects=False,
        timeout=30,
    )
    if login_resp.status_code != 302:
        raise AssertionError(
            f"Session login failed: HTTP {login_resp.status_code} - "
            f"{login_resp.text[:300]}"
        )
    response = session.get(settings_url, allow_redirects=False, timeout=30)
    if response.status_code != 200:
        raise AssertionError(
            f"Settings tab failed: {settings_url} -> HTTP {response.status_code}"
        )
    if 'name="overwrite_vm_tags"' not in response.text:
        raise AssertionError(
            f"Settings tab missing overwrite_vm_tags form field at {settings_url}"
        )
    # Regression for issue #342: the overwrite_device_type flag must render so
    # users can disable device-type drift on VM and node sync runs.
    if 'name="overwrite_device_type"' not in response.text:
        raise AssertionError(
            f"Settings tab missing overwrite_device_type form field at {settings_url}"
        )

    keepalive_checks = [
        (
            "fastapi",
            f"{netbox_base_url}/plugins/proxbox/keepalive-status/fastapi/{endpoint_ids['fastapi_pk']}/",
        ),
        (
            "netbox",
            f"{netbox_base_url}/plugins/proxbox/keepalive-status/netbox/{endpoint_ids['netbox_pk']}/",
        ),
    ]
    if service == "pve":
        keepalive_checks.append(
            (
                "proxmox",
                f"{netbox_base_url}/plugins/proxbox/keepalive-status/proxmox/{endpoint_ids['proxmox_pk']}/",
            )
        )
    else:
        log_service_skip(service, "Proxmox keepalive status check")

    for service_slug, url in keepalive_checks:
        print(f"Checking keepalive: {url}")
        response = requests.get(url, headers=headers, timeout=30)
        print(
            f"Keepalive response: HTTP {response.status_code} - {response.text[:500]}"
        )
        payload = assert_ok(response, context=f"keepalive {url}")
        _assert_status_shape(payload, context=f"keepalive {service_slug}")
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


def create_proxbox_custom_fields(
    proxbox_base_url: str, *, proxbox_api_key: str = ""
) -> None:
    """Call proxbox-api to create all Proxmox custom fields in NetBox.

    Must be called before any device sync so that the proxmox_last_updated
    custom field exists in NetBox when device prerequisites are written.
    """
    headers: dict[str, str] = (
        {"X-Proxbox-API-Key": proxbox_api_key} if proxbox_api_key else {}
    )
    print("Creating Proxmox custom fields in NetBox via proxbox-api...")
    response = requests.get(
        f"{proxbox_base_url}/extras/extras/custom-fields/create",
        headers=headers,
        timeout=60,
    )
    assert_ok(response, context="create proxmox custom fields")
    print(f"Custom fields created: {len(response.json())} field(s)")
