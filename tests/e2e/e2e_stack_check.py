from __future__ import annotations

import json
import os
import time
from collections.abc import Iterable

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


def _trigger_and_wait_sync(netbox_base_url: str, netbox_token: str) -> None:
    headers = {
        "Authorization": f"Token {netbox_token}",
        "Accept": "application/json",
    }
    trigger = requests.post(
        f"{netbox_base_url}/plugins/proxbox/sync/full-update/",
        headers=headers,
        timeout=30,
        allow_redirects=False,
    )
    if trigger.status_code not in (302, 303):
        raise AssertionError(
            f"Sync trigger did not redirect as expected: HTTP {trigger.status_code} {trigger.text}"
        )

    jobs_url = f"{netbox_base_url}/api/core/jobs/?limit=20"
    deadline = time.time() + 600
    terminal_statuses = {"completed", "errored", "failed"}

    while time.time() < deadline:
        jobs_response = requests.get(jobs_url, headers=headers, timeout=30)
        jobs_payload = _assert_ok(jobs_response, context="list jobs")
        results: Iterable[dict] = jobs_payload.get("results", [])
        proxbox_jobs = [
            job
            for job in results
            if str(job.get("name", "")).startswith("Proxbox Sync")
        ]
        if proxbox_jobs:
            latest = proxbox_jobs[0]
            status = str(latest.get("status", "")).lower()
            if status in terminal_statuses:
                if status != "completed":
                    raise AssertionError(
                        f"Proxbox sync job failed with status={status}: {latest}"
                    )
                return
        time.sleep(5)

    raise AssertionError("Timed out waiting for Proxbox sync job completion")


def _assert_synced_data(netbox_base_url: str, netbox_token: str) -> None:
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


def _assert_backend_stream(proxbox_base_url: str) -> None:
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


def main() -> None:
    netbox_base_url = _must_getenv("NETBOX_BASE_URL")
    proxbox_base_url = _must_getenv("PROXBOX_BASE_URL")
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
    _trigger_and_wait_sync(netbox_base_url, netbox_token)
    _assert_synced_data(netbox_base_url, netbox_token)
    _assert_backend_stream(proxbox_base_url)
    print("E2E stack test succeeded")


if __name__ == "__main__":
    main()
