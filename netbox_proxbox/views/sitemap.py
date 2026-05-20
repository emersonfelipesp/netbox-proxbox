"""Plain-text sitemap of all browsable Proxbox plugin pages."""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.views import View
from utilities.views import ConditionalLoginRequiredMixin

from netbox_proxbox import __version__

_PLUGIN = "plugins/proxbox"

# (label, path-relative-to-plugin-root)
_SECTIONS: list[tuple[str, list[tuple[str, str]]]] = [
    (
        "Meta",
        [
            ("Homepage", ""),
            ("Dashboard", "dashboard/"),
            ("HA Status", "ha/"),
            ("Sitemap (this page)", "sitemap.txt"),
        ],
    ),
    (
        "Infrastructure",
        [
            ("Clusters", "clusters/"),
            ("Nodes", "nodes/"),
            ("Storage (list)", "storage/"),
            ("Storage (add)", "storage/add/"),
        ],
    ),
    (
        "Virtualization",
        [
            ("Virtual Machines", "virtual_machines/"),
            ("LXC Containers", "lxc_containers/"),
            ("Virtual Disks", "virtual-disks/"),
            ("VM Interfaces", "interfaces/"),
            ("IP Addresses", "ip-addresses/"),
            ("VM Cloud-Init (list)", "vm-cloudinit/"),
            ("VM Cloud-Init (add)", "vm-cloudinit/add/"),
            ("Cloud Image Templates (list)", "cloud-image-templates/"),
            ("Cloud Image Templates (add)", "cloud-image-templates/add/"),
        ],
    ),
    (
        "Firewall / Security",
        [
            ("Firewall Rules (list)", "firewall/rules/"),
            ("Firewall Rules (add)", "firewall/rules/add/"),
            ("Security Groups (list)", "firewall/security-groups/"),
            ("Security Groups (add)", "firewall/security-groups/add/"),
            ("IP Sets (list)", "firewall/ipsets/"),
            ("IP Sets (add)", "firewall/ipsets/add/"),
            ("IP Set Entries (list)", "firewall/ipset-entries/"),
            ("IP Set Entries (add)", "firewall/ipset-entries/add/"),
            ("Aliases (list)", "firewall/aliases/"),
            ("Aliases (add)", "firewall/aliases/add/"),
            ("Firewall Options (list)", "firewall/options/"),
        ],
    ),
    (
        "Data Protection",
        [
            ("VM Backups (list)", "backups/"),
            ("Backup Routines (list)", "backup-routines/"),
            ("Backup Routines (add)", "backup-routines/add/"),
            ("VM Snapshots (list)", "snapshots/"),
            ("Replications (list)", "replications/"),
            ("Replications (add)", "replications/add/"),
            ("Task History (list)", "task-history/"),
        ],
    ),
    (
        "Sync & Operations",
        [
            ("Schedule Sync", "sync/schedule/"),
            ("Apply Jobs", "intent/apply-jobs/"),
            ("Deletion Requests", "intent/deletion-requests/"),
            ("Backend Logs", "logs/"),
        ],
    ),
    (
        "Configuration",
        [
            ("Plugin Settings", "settings/"),
            ("Proxmox Endpoints (list)", "endpoints/proxmox/"),
            ("Proxmox Endpoints (add)", "endpoints/proxmox/add/"),
            ("NetBox Endpoints (list)", "endpoints/netbox/"),
            ("NetBox Endpoints (add)", "endpoints/netbox/add/"),
            ("FastAPI Endpoints (list)", "endpoints/fastapi/"),
            ("FastAPI Endpoints (add)", "endpoints/fastapi/add/"),
            ("SSH Credentials (list)", "ssh-credentials/"),
            ("SSH Credentials (add)", "ssh-credentials/add/"),
        ],
    ),
    (
        "Community",
        [
            ("Contributing", "contributing/"),
            ("Community", "community/"),
        ],
    ),
]

_PK_PAGES: list[tuple[str, str]] = [
    ("Proxmox Endpoint detail", "endpoints/proxmox/{pk}/"),
    ("Proxmox Endpoint edit", "endpoints/proxmox/{pk}/edit/"),
    ("Proxmox Endpoint delete", "endpoints/proxmox/{pk}/delete/"),
    ("Proxmox Endpoint settings", "endpoints/proxmox/{pk}/settings/"),
    ("NetBox Endpoint detail", "endpoints/netbox/{pk}/"),
    ("NetBox Endpoint edit", "endpoints/netbox/{pk}/edit/"),
    ("FastAPI Endpoint detail", "endpoints/fastapi/{pk}/"),
    ("FastAPI Endpoint edit", "endpoints/fastapi/{pk}/edit/"),
    ("SSH Credential detail", "ssh-credentials/{pk}/"),
    ("SSH Credential edit", "ssh-credentials/{pk}/edit/"),
    ("Storage detail", "storage/{pk}/"),
    ("Storage edit", "storage/{pk}/edit/"),
    ("VM Backup detail", "backups/{pk}/"),
    ("Backup Routine detail", "backup-routines/{pk}/"),
    ("Backup Routine edit", "backup-routines/{pk}/edit/"),
    ("Replication detail", "replications/{pk}/"),
    ("Snapshot detail", "snapshots/{pk}/"),
    ("Task History detail", "task-history/{pk}/"),
    ("Cloud Image Template detail", "cloud-image-templates/{pk}/"),
    ("Firewall Rule detail", "firewall/rules/{pk}/"),
    ("Security Group detail", "firewall/security-groups/{pk}/"),
    ("IP Set detail", "firewall/ipsets/{pk}/"),
    ("IP Set Entry detail", "firewall/ipset-entries/{pk}/"),
    ("Alias detail", "firewall/aliases/{pk}/"),
    ("Firewall Options detail", "firewall/options/{pk}/"),
]


def _build_sitemap(base: str) -> list[str]:
    plugin_base = f"{base}/{_PLUGIN}"
    lines: list[str] = [
        f"# Proxbox plugin sitemap  —  netbox-proxbox {__version__}",
        f"# Base: {plugin_base}",
        "",
    ]
    for section_name, entries in _SECTIONS:
        lines.append(f"## {section_name}")
        for label, rel in entries:
            lines.append(f"{plugin_base}/{rel}  # {label}")
        lines.append("")

    lines.append("# Detail / edit / delete pages (require a valid pk)")
    lines.append("# Discover pks via /api/plugins/proxbox/")
    for label, rel in _PK_PAGES:
        lines.append(f"# {plugin_base}/{rel}  # {label}")
    return lines


class SitemapView(ConditionalLoginRequiredMixin, View):
    """Return a plain-text sitemap of all Proxbox plugin pages."""

    def get(self, request: HttpRequest) -> HttpResponse:
        base = request.build_absolute_uri("/").rstrip("/")
        body = "\n".join(_build_sitemap(base)) + "\n"
        return HttpResponse(body, content_type="text/plain; charset=utf-8")
