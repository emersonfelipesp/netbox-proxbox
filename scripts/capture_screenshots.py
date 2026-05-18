"""Capture Playwright screenshots of the netbox-proxbox plugin UI.

Usage:
    pip install playwright requests
    playwright install chromium
    python scripts/capture_screenshots.py

Required environment variables (all set by docs-screenshots.yml automatically):
    NETBOX_BASE_URL        http://127.0.0.1:18080
    PROXBOX_BASE_URL       http://127.0.0.1:18800
    PROXMOX_MOCK_BASE_URL  https://127.0.0.1:18006
    NETBOX_PUBLIC_URL      http://<container-ip>:8080
    NETBOX_API_TOKEN       (NetBox admin token)
    NETBOX_TOKEN_ID        (integer id of that token)
    PROXMOX_MOCK_IP        (container IP of proxmox mock)
    PROXBOX_API_IP         (container IP of proxbox-api)

Optional:
    SCREENSHOTS_DIR        path to write PNGs (default: docs/assets/screenshots)
"""

from __future__ import annotations

import os
import pathlib
import sys

# Reuse the e2e test helpers — no code duplication.
_REPO_ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(_REPO_ROOT / "tests" / "e2e"))

import requests  # noqa: E402

from stack_common import must_getenv, wait_http_ok  # noqa: E402
from stack_setup import (  # noqa: E402
    create_proxbox_custom_fields,
    ensure_netbox_plugin_endpoints,
    ensure_proxbox_backend_endpoints,
    register_proxbox_api_key,
)
from stack_sync import trigger_and_wait_sync  # noqa: E402


# List-view pages: (slug, url-path-relative-to-base)
PAGES: list[tuple[str, str]] = [
    ("home", "/plugins/proxbox/"),
    ("dashboard", "/plugins/proxbox/dashboard/"),
    ("proxmox-endpoints", "/plugins/proxbox/endpoints/proxmox/"),
    ("fastapi-endpoints", "/plugins/proxbox/endpoints/fastapi/"),
    ("netbox-endpoints", "/plugins/proxbox/endpoints/netbox/"),
    ("clusters", "/plugins/proxbox/clusters/"),
    ("nodes", "/plugins/proxbox/nodes/"),
    ("virtual-machines", "/plugins/proxbox/virtual_machines/"),
    ("lxc-containers", "/plugins/proxbox/lxc_containers/"),
    ("storage", "/plugins/proxbox/storage/"),
    ("backups", "/plugins/proxbox/backups/"),
    ("snapshots", "/plugins/proxbox/snapshots/"),
    ("backup-routines", "/plugins/proxbox/backup-routines/"),
    ("replications", "/plugins/proxbox/replications/"),
    ("task-history", "/plugins/proxbox/task-history/"),
]

# Detail pages: (slug, detail_url_template, api_path, query_params)
# api_path is queried to discover the first object's pk; {id} in the template is replaced.
DETAIL_SPECS: list[tuple[str, str, str, dict]] = [
    (
        "proxmox-endpoint-detail",
        "/plugins/proxbox/endpoints/proxmox/{id}/",
        "/api/plugins/proxbox/endpoints/proxmox/",
        {},
    ),
    (
        "proxmox-endpoint-settings",
        "/plugins/proxbox/endpoints/proxmox/{id}/settings/",
        "/api/plugins/proxbox/endpoints/proxmox/",
        {},
    ),
    (
        "netbox-endpoint-detail",
        "/plugins/proxbox/endpoints/netbox/{id}/",
        "/api/plugins/proxbox/endpoints/netbox/",
        {},
    ),
    (
        "fastapi-endpoint-detail",
        "/plugins/proxbox/endpoints/fastapi/{id}/",
        "/api/plugins/proxbox/endpoints/fastapi/",
        {},
    ),
    (
        "storage-detail",
        "/plugins/proxbox/storage/{id}/",
        "/api/plugins/proxbox/storage/",
        {},
    ),
    (
        "backup-detail",
        "/plugins/proxbox/backups/{id}/",
        "/api/plugins/proxbox/backups/",
        {},
    ),
    (
        "backup-routine-detail",
        "/plugins/proxbox/backup-routines/{id}/",
        "/api/plugins/proxbox/backup-routines/",
        {},
    ),
    (
        "replication-detail",
        "/plugins/proxbox/replications/{id}/",
        "/api/plugins/proxbox/replications/",
        {},
    ),
    (
        "snapshot-detail",
        "/plugins/proxbox/snapshots/{id}/",
        "/api/plugins/proxbox/snapshots/",
        {},
    ),
    (
        "task-history-detail",
        "/plugins/proxbox/task-history/{id}/",
        "/api/plugins/proxbox/task-history/",
        {},
    ),
    (
        "virtual-machine-detail",
        "/virtualization/virtual-machines/{id}/",
        "/api/virtualization/virtual-machines/",
        {},
    ),
    (
        "lxc-container-detail",
        "/virtualization/virtual-machines/{id}/",
        "/api/virtualization/virtual-machines/",
        {"name": "e2e-lxc-102"},
    ),
]


def seed_data(
    netbox_base_url: str,
    proxbox_base_url: str,
    netbox_token: str,
    netbox_token_id: int,
    netbox_public_url: str,
) -> None:
    print("Registering proxbox-api key...")
    proxbox_api_key = register_proxbox_api_key(proxbox_base_url)

    print("Configuring proxbox-api backend endpoints...")
    ensure_proxbox_backend_endpoints(
        proxbox_base_url,
        netbox_public_url,
        netbox_token,
        proxbox_api_key=proxbox_api_key,
    )

    print("Creating NetBox plugin endpoint objects...")
    endpoint_ids = ensure_netbox_plugin_endpoints(
        netbox_base_url,
        netbox_token,
        netbox_token_id,
        netbox_public_url=netbox_public_url,
        proxbox_api_key=proxbox_api_key,
    )

    print(
        "Triggering Proxmox keepalive to register endpoint with proxbox-api backend..."
    )
    keepalive_resp = requests.get(
        f"{netbox_base_url}/plugins/proxbox/keepalive-status/proxmox/{endpoint_ids['proxmox_pk']}/",
        headers={"Authorization": f"Token {netbox_token}"},
        timeout=30,
    )
    keepalive_resp.raise_for_status()

    print("Creating Proxbox custom fields...")
    create_proxbox_custom_fields(proxbox_base_url, proxbox_api_key=proxbox_api_key)

    # Run each sync stage individually in dependency order (same as e2e tests).
    # The full-update route streams all stages in one proxbox-api call and fails
    # when VM deps (cluster, device, role) haven't been committed yet at that point.
    _STAGES = [
        ("/plugins/proxbox/sync/devices/", "devices"),
        ("/plugins/proxbox/sync/storage/", "storage"),
        ("/plugins/proxbox/sync/virtual-machines/", "virtual machines"),
        ("/plugins/proxbox/sync/virtual-machines/virtual-disks/", "virtual disks"),
        ("/plugins/proxbox/sync/virtual-machines/backups/", "vm backups"),
        ("/plugins/proxbox/sync/virtual-machines/snapshots/", "vm snapshots"),
        ("/plugins/proxbox/sync/network-interfaces/", "network interfaces"),
        ("/plugins/proxbox/sync/ip-addresses/", "ip addresses"),
        ("/plugins/proxbox/sync/replications/", "replications"),
        ("/plugins/proxbox/sync/backup-routines/", "backup routines"),
    ]
    for route, fragment in _STAGES:
        print(f"  Syncing stage: {fragment}...")
        trigger_and_wait_sync(
            netbox_base_url,
            netbox_token,
            route=route,
            expected_name_fragment=fragment,
        )
    print("Sync complete. NetBox is populated with mock data.")


def fetch_first_id(
    netbox_base_url: str,
    netbox_token: str,
    api_path: str,
    params: dict | None = None,
) -> int | None:
    resp = requests.get(
        f"{netbox_base_url}{api_path}",
        params=params or {},
        headers={
            "Authorization": f"Token {netbox_token}",
            "Accept": "application/json",
        },
        timeout=30,
    )
    resp.raise_for_status()
    results = resp.json().get("results", [])
    return results[0]["id"] if results else None


def login(page, base_url: str) -> None:
    page.goto(f"{base_url}/login/")
    page.fill("#id_username", "admin")
    page.fill("#id_password", "admin")
    page.click("[type=submit]")
    page.wait_for_load_state("load")
    print(f"Logged in to NetBox at {base_url}")


def capture(page, base_url: str, slug: str, path: str, out_dir: pathlib.Path) -> None:
    url = f"{base_url}{path}"
    print(f"  Capturing {slug} -> {url}")
    page.goto(url)
    page.wait_for_load_state("load")
    # Short pause so initial JS renders (keepalive cards, etc.)
    page.wait_for_timeout(2000)
    dest = out_dir / f"{slug}.png"
    page.screenshot(path=str(dest), full_page=True)
    print(f"  Saved: {dest}")


def capture_detail_pages(
    page,
    netbox_base_url: str,
    netbox_token: str,
    out_dir: pathlib.Path,
) -> int:
    captured = 0
    for slug, url_tpl, api_path, params in DETAIL_SPECS:
        obj_id = fetch_first_id(netbox_base_url, netbox_token, api_path, params)
        if obj_id is None:
            print(
                f"  Skipping {slug}: no objects found at {api_path} (params={params})"
            )
            continue
        path = url_tpl.format(id=obj_id)
        capture(page, netbox_base_url, slug, path, out_dir)
        captured += 1
    return captured


def main() -> None:
    netbox_base_url = must_getenv("NETBOX_BASE_URL")
    proxbox_base_url = must_getenv("PROXBOX_BASE_URL")
    netbox_public_url = must_getenv("NETBOX_PUBLIC_URL")
    netbox_token = must_getenv("NETBOX_API_TOKEN")
    netbox_token_id = int(must_getenv("NETBOX_TOKEN_ID"))

    screenshots_dir = pathlib.Path(
        os.getenv(
            "SCREENSHOTS_DIR", str(_REPO_ROOT / "docs" / "assets" / "screenshots")
        )
    )
    screenshots_dir.mkdir(parents=True, exist_ok=True)

    print(f"Screenshots will be written to: {screenshots_dir}")

    print("Waiting for services to be ready...")
    wait_http_ok(f"{netbox_base_url}/api/")
    wait_http_ok(f"{proxbox_base_url}/")

    seed_data(
        netbox_base_url,
        proxbox_base_url,
        netbox_token,
        netbox_token_id,
        netbox_public_url,
    )

    from playwright.sync_api import sync_playwright  # noqa: PLC0415

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        login(page, netbox_base_url)

        print(f"Capturing {len(PAGES)} list-view pages...")
        for slug, path in PAGES:
            capture(page, netbox_base_url, slug, path, screenshots_dir)

        print(f"Capturing up to {len(DETAIL_SPECS)} detail pages...")
        detail_count = capture_detail_pages(
            page, netbox_base_url, netbox_token, screenshots_dir
        )

        browser.close()

    total = len(PAGES) + detail_count
    print(f"\nDone. {total} screenshots written to {screenshots_dir}")
    print(f"  List views: {len(PAGES)}")
    print(f"  Detail views: {detail_count}")


if __name__ == "__main__":
    main()
