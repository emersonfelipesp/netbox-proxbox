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
    ensure_netbox_plugin_endpoints,
    ensure_proxbox_backend_endpoints,
    register_proxbox_api_key,
)
from stack_sync import trigger_and_wait_sync  # noqa: E402


# Pages to capture: (slug, url-path-relative-to-base)
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

    # proxbox-api 0.0.7 registers proxmox_last_updated with only 6 object types
    # (missing dcim.device, virtualization.cluster, virtualization.virtualmachine etc.)
    # via its CreateCustomFieldsDep dependency that runs at VM-sync startup.
    # Strategy:
    #   1. Pre-call proxbox-api's create_custom_fields endpoint to populate its
    #      module-level cache. Subsequent CreateCustomFieldsDep calls during VM sync
    #      return the cached result without re-contacting NetBox, so our broader
    #      13-type registration below is never overwritten.
    #   2. PATCH proxmox_last_updated in NetBox to include all types the sync code uses.
    print("Pre-loading proxbox-api custom fields cache...")
    _warmup_resp = requests.get(
        f"{proxbox_base_url}/extras/extras/custom-fields/create",
        headers={"X-Proxbox-API-Key": proxbox_api_key},
        timeout=120,
    )
    if _warmup_resp.status_code == 200:
        print("Proxbox-api custom fields cache populated successfully")
    else:
        print(
            f"Warning: custom fields warmup returned HTTP {_warmup_resp.status_code} — "
            "continuing; VM sync may still fail if CreateCustomFieldsDep overwrites the field"
        )

    # Ensure proxmox_last_updated covers ALL types used by 0.0.7's sync code.
    # This runs after the warmup so the cache is already warm and won't re-patch.
    print("Ensuring proxmox_last_updated covers all required object types...")
    _CF_OBJECT_TYPES = [
        "dcim.device",
        "dcim.devicerole",
        "dcim.devicetype",
        "dcim.interface",
        "dcim.manufacturer",
        "dcim.site",
        "ipam.ipaddress",
        "ipam.vlan",
        "virtualization.cluster",
        "virtualization.clustertype",
        "virtualization.virtualdisk",
        "virtualization.virtualmachine",
        "virtualization.vminterface",
    ]
    _CF_PAYLOAD = {
        "object_types": _CF_OBJECT_TYPES,
        "type": "datetime",
        "name": "proxmox_last_updated",
        "label": "Last Updated",
        "description": "Proxmox Plugin last modified this object",
        "ui_visible": "always",
        "ui_editable": "hidden",
        "weight": 200,
        "filter_logic": "loose",
        "search_weight": 1000,
        "group_name": "Proxmox",
    }
    _cf_headers = {
        "Authorization": f"Token {netbox_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    # Look up the field to decide create vs patch.
    _lookup_resp = requests.get(
        f"{netbox_base_url}/api/extras/custom-fields/",
        params={"name": "proxmox_last_updated"},
        headers=_cf_headers,
        timeout=30,
    )
    _lookup_resp.raise_for_status()
    _existing = _lookup_resp.json().get("results", [])
    if _existing:
        _field_id = _existing[0]["id"]
        _patch_resp = requests.patch(
            f"{netbox_base_url}/api/extras/custom-fields/{_field_id}/",
            json={"object_types": _CF_OBJECT_TYPES},
            headers=_cf_headers,
            timeout=30,
        )
        _patch_resp.raise_for_status()
        print("Custom field proxmox_last_updated: patched to 13 object types")
    else:
        _create_resp = requests.post(
            f"{netbox_base_url}/api/extras/custom-fields/",
            json=_CF_PAYLOAD,
            headers=_cf_headers,
            timeout=30,
        )
        _create_resp.raise_for_status()
        print("Custom field proxmox_last_updated: created with 13 object types")

    print("Creating NetBox plugin endpoint objects...")
    ensure_netbox_plugin_endpoints(
        netbox_base_url,
        netbox_token,
        netbox_token_id,
        netbox_public_url=netbox_public_url,
        proxbox_api_key=proxbox_api_key,
    )

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
        print(f"Capturing {len(PAGES)} pages...")
        for slug, path in PAGES:
            capture(page, netbox_base_url, slug, path, screenshots_dir)
        browser.close()

    print(f"\nDone. {len(PAGES)} screenshots written to {screenshots_dir}")


if __name__ == "__main__":
    main()
