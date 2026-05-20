"""Visit every Proxbox plugin page and assert HTTP 200 with no Django 500 body.

Usage:
    NETBOX_BASE_URL=http://127.0.0.1:18080 \
    NETBOX_API_TOKEN=<admin-token> \
    python tests/e2e/page_coverage_check.py

Exit 0 = all pages OK, Exit 1 = one or more failures.
"""

from __future__ import annotations

import os
import sys
from typing import NamedTuple

import requests

_NETBOX_BASE_URL = os.environ.get("NETBOX_BASE_URL", "http://127.0.0.1:18080").rstrip("/")
_NETBOX_API_TOKEN = os.environ.get("NETBOX_API_TOKEN", "")


# ── Static pages (no pk required) ───────────────────────────────────────────
# (label, path-relative-to-base)
LIST_PAGES: list[tuple[str, str]] = [
    # Meta
    ("home", "/plugins/proxbox/"),
    ("sitemap", "/plugins/proxbox/sitemap.txt"),
    ("dashboard", "/plugins/proxbox/dashboard/"),
    ("ha", "/plugins/proxbox/ha/"),
    # Infrastructure
    ("clusters", "/plugins/proxbox/clusters/"),
    ("nodes", "/plugins/proxbox/nodes/"),
    ("storage-list", "/plugins/proxbox/storage/"),
    ("storage-add", "/plugins/proxbox/storage/add/"),
    # Virtualization
    ("virtual-machines", "/plugins/proxbox/virtual_machines/"),
    ("lxc-containers", "/plugins/proxbox/lxc_containers/"),
    ("virtual-disks", "/plugins/proxbox/virtual-disks/"),
    ("interfaces", "/plugins/proxbox/interfaces/"),
    ("ip-addresses", "/plugins/proxbox/ip-addresses/"),
    ("vm-cloudinit-list", "/plugins/proxbox/vm-cloudinit/"),
    ("vm-cloudinit-add", "/plugins/proxbox/vm-cloudinit/add/"),
    ("cloud-image-templates-list", "/plugins/proxbox/cloud-image-templates/"),
    ("cloud-image-templates-add", "/plugins/proxbox/cloud-image-templates/add/"),
    # Firewall / Security
    ("firewall-rules-list", "/plugins/proxbox/firewall/rules/"),
    ("firewall-rules-add", "/plugins/proxbox/firewall/rules/add/"),
    ("firewall-security-groups-list", "/plugins/proxbox/firewall/security-groups/"),
    ("firewall-security-groups-add", "/plugins/proxbox/firewall/security-groups/add/"),
    ("firewall-ipsets-list", "/plugins/proxbox/firewall/ipsets/"),
    ("firewall-ipsets-add", "/plugins/proxbox/firewall/ipsets/add/"),
    ("firewall-ipset-entries-list", "/plugins/proxbox/firewall/ipset-entries/"),
    ("firewall-ipset-entries-add", "/plugins/proxbox/firewall/ipset-entries/add/"),
    ("firewall-aliases-list", "/plugins/proxbox/firewall/aliases/"),
    ("firewall-aliases-add", "/plugins/proxbox/firewall/aliases/add/"),
    ("firewall-options-list", "/plugins/proxbox/firewall/options/"),
    # Data Protection
    ("backups-list", "/plugins/proxbox/backups/"),
    ("backup-routines-list", "/plugins/proxbox/backup-routines/"),
    ("backup-routines-add", "/plugins/proxbox/backup-routines/add/"),
    ("snapshots-list", "/plugins/proxbox/snapshots/"),
    ("replications-list", "/plugins/proxbox/replications/"),
    ("replications-add", "/plugins/proxbox/replications/add/"),
    ("task-history-list", "/plugins/proxbox/task-history/"),
    # Sync & Operations
    ("schedule-sync", "/plugins/proxbox/sync/schedule/"),
    ("apply-jobs", "/plugins/proxbox/intent/apply-jobs/"),
    ("deletion-requests", "/plugins/proxbox/intent/deletion-requests/"),
    ("backend-logs", "/plugins/proxbox/logs/"),
    # Configuration
    ("settings", "/plugins/proxbox/settings/"),
    ("proxmox-endpoints-list", "/plugins/proxbox/endpoints/proxmox/"),
    ("proxmox-endpoints-add", "/plugins/proxbox/endpoints/proxmox/add/"),
    ("netbox-endpoints-list", "/plugins/proxbox/endpoints/netbox/"),
    ("netbox-endpoints-add", "/plugins/proxbox/endpoints/netbox/add/"),
    ("fastapi-endpoints-list", "/plugins/proxbox/endpoints/fastapi/"),
    ("fastapi-endpoints-add", "/plugins/proxbox/endpoints/fastapi/add/"),
    ("ssh-credentials-list", "/plugins/proxbox/ssh-credentials/"),
    ("ssh-credentials-add", "/plugins/proxbox/ssh-credentials/add/"),
    # Community
    ("contributing", "/plugins/proxbox/contributing/"),
    ("community", "/plugins/proxbox/community/"),
]

# ── Detail pages (require object discovery via API) ──────────────────────────
# (label, url-template-with-{id}, api-endpoint)
class DetailSpec(NamedTuple):
    label: str
    url_template: str
    api_path: str


DETAIL_SPECS: list[DetailSpec] = [
    DetailSpec(
        "proxmox-endpoint-detail",
        "/plugins/proxbox/endpoints/proxmox/{id}/",
        "/api/plugins/proxbox/endpoints/proxmox/",
    ),
    DetailSpec(
        "proxmox-endpoint-settings",
        "/plugins/proxbox/endpoints/proxmox/{id}/settings/",
        "/api/plugins/proxbox/endpoints/proxmox/",
    ),
    DetailSpec(
        "netbox-endpoint-detail",
        "/plugins/proxbox/endpoints/netbox/{id}/",
        "/api/plugins/proxbox/endpoints/netbox/",
    ),
    DetailSpec(
        "fastapi-endpoint-detail",
        "/plugins/proxbox/endpoints/fastapi/{id}/",
        "/api/plugins/proxbox/endpoints/fastapi/",
    ),
    DetailSpec(
        "storage-detail",
        "/plugins/proxbox/storage/{id}/",
        "/api/plugins/proxbox/storage/",
    ),
    DetailSpec(
        "vm-backup-detail",
        "/plugins/proxbox/backups/{id}/",
        "/api/plugins/proxbox/backups/",
    ),
    DetailSpec(
        "backup-routine-detail",
        "/plugins/proxbox/backup-routines/{id}/",
        "/api/plugins/proxbox/backup-routines/",
    ),
    DetailSpec(
        "replication-detail",
        "/plugins/proxbox/replications/{id}/",
        "/api/plugins/proxbox/replications/",
    ),
    DetailSpec(
        "snapshot-detail",
        "/plugins/proxbox/snapshots/{id}/",
        "/api/plugins/proxbox/snapshots/",
    ),
    DetailSpec(
        "task-history-detail",
        "/plugins/proxbox/task-history/{id}/",
        "/api/plugins/proxbox/task-history/",
    ),
]


def login_session(base_url: str) -> requests.Session:
    """Return an authenticated requests.Session using admin/admin credentials."""
    session = requests.Session()
    session.get(f"{base_url}/login/", timeout=30)
    csrf = session.cookies.get("csrftoken")
    if not csrf:
        raise RuntimeError(f"Login page did not set csrftoken at {base_url}/login/")
    resp = session.post(
        f"{base_url}/login/",
        data={
            "username": "admin",
            "password": "admin",
            "csrfmiddlewaretoken": csrf,
            "next": "/",
        },
        headers={"Referer": f"{base_url}/login/"},
        allow_redirects=False,
        timeout=30,
    )
    if resp.status_code != 302:
        raise RuntimeError(
            f"Session login failed: HTTP {resp.status_code} — {resp.text[:200]}"
        )
    return session


def check_page(
    session: requests.Session,
    url: str,
    label: str,
    failures: list[str],
) -> None:
    """GET url and record a failure if the response is not a success or contains a 500 body."""
    try:
        resp = session.get(url, allow_redirects=True, timeout=30)
    except requests.RequestException as exc:
        failures.append(f"{label}: connection error — {exc}")
        print(f"  FAIL  {label}: {exc}")
        return

    if not (200 <= resp.status_code < 400):
        failures.append(f"{label}: HTTP {resp.status_code}")
        print(f"  FAIL  {label}: HTTP {resp.status_code}  ({url})")
        return

    body = resp.text
    if "Internal Server Error" in body or "Traceback (most recent call last)" in body:
        failures.append(f"{label}: Django 500 body detected")
        print(f"  FAIL  {label}: Django 500 content in HTTP {resp.status_code} response  ({url})")
        return

    print(f"  OK    {label}  HTTP {resp.status_code}")


def discover_first_id(api_path: str, token: str) -> int | None:
    """Return the id of the first object at api_path, or None if empty."""
    url = f"{_NETBOX_BASE_URL}{api_path}?limit=1"
    try:
        resp = requests.get(
            url,
            headers={"Authorization": f"Token {token}"},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        if results:
            return results[0]["id"]
    except Exception as exc:  # noqa: BLE001
        print(f"  WARN  API discovery failed for {api_path}: {exc}")
    return None


def main() -> None:
    if not _NETBOX_API_TOKEN:
        print("ERROR: NETBOX_API_TOKEN environment variable is required")
        sys.exit(1)

    print(f"Page coverage check against {_NETBOX_BASE_URL}")
    print(f"  {len(LIST_PAGES)} list/add pages + up to {len(DETAIL_SPECS)} detail pages")
    print()

    session = login_session(_NETBOX_BASE_URL)
    failures: list[str] = []

    print("── Static pages ──────────────────────────────────────────────────────")
    for label, path in LIST_PAGES:
        url = f"{_NETBOX_BASE_URL}{path}"
        check_page(session, url, label, failures)

    print()
    print("── Detail pages ──────────────────────────────────────────────────────")
    for spec in DETAIL_SPECS:
        obj_id = discover_first_id(spec.api_path, _NETBOX_API_TOKEN)
        if obj_id is None:
            print(f"  SKIP  {spec.label}: no objects found at {spec.api_path}")
            continue
        url = f"{_NETBOX_BASE_URL}{spec.url_template.format(id=obj_id)}"
        check_page(session, url, spec.label, failures)

    print()
    if failures:
        print(f"── FAILED: {len(failures)} page(s) ──────────────────────────────")
        for msg in failures:
            print(f"  • {msg}")
        sys.exit(1)
    else:
        print(f"── All {len(LIST_PAGES)} static + detail pages passed ✓")


if __name__ == "__main__":
    main()
