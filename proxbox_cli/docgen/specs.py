"""Capture specs for generated Proxbox CLI documentation."""

from proxbox_cli.docgen.models import CaptureSpec


def load_specs() -> list[CaptureSpec]:
    """Return the curated CLI captures shown in the generated docs."""
    return [
        CaptureSpec(
            section="Core Commands",
            title="Root Help",
            argv=["--help"],
            notes="Top-level entrypoint and root command groups.",
        ),
        CaptureSpec(
            section="Core Commands",
            title="Init Help",
            argv=["init", "--help"],
            notes="Interactive configuration bootstrap for the proxbox-api base URL.",
        ),
        CaptureSpec(
            section="Core Commands",
            title="Docs Generate Capture Help",
            argv=["docs", "generate-capture", "--help"],
            notes="Regenerates the machine-generated CLI reference artifacts used by MkDocs.",
        ),
        CaptureSpec(
            section="Core Commands",
            title="Extras Help",
            argv=["extras", "--help"],
            notes="Shows extras-related CLI commands (custom fields, etc.).",
        ),
        CaptureSpec(
            section="Core Commands",
            title="Proxbox Help",
            argv=["proxbox", "--help"],
            notes="Plugin configuration and backend info commands.",
        ),
        CaptureSpec(
            section="NetBox Commands",
            title="NetBox Help",
            argv=["netbox", "--help"],
            notes="NetBox status, OpenAPI, and endpoint CRUD commands.",
        ),
        CaptureSpec(
            section="NetBox Commands",
            title="NetBox Endpoint Create Help",
            argv=["netbox", "endpoint", "create", "--help"],
            notes="Payload-driven endpoint creation command.",
        ),
        CaptureSpec(
            section="Proxmox Commands",
            title="Proxmox Help",
            argv=["proxmox", "--help"],
            notes="Cluster, node, viewer, and endpoint commands.",
        ),
        CaptureSpec(
            section="Proxmox Commands",
            title="Proxmox Viewer Generate Help",
            argv=["proxmox", "viewer", "generate", "--help"],
            notes="Code-generation pipeline entrypoint for the proxmox viewer endpoints.",
        ),
        CaptureSpec(
            section="Proxmox Commands",
            title="Proxmox Storage Content Help",
            argv=["proxmox", "storage-content", "--help"],
            notes="Example of a command with required arguments and optional filters.",
        ),
        CaptureSpec(
            section="Proxmox Commands",
            title="Proxmox Nodes LXC Help",
            argv=["proxmox", "nodes", "lxc", "--help"],
            notes="LXC container listing on a specific node.",
        ),
        CaptureSpec(
            section="Infrastructure Commands",
            title="DCIM Help",
            argv=["dcim", "--help"],
            notes="Node device and interface sync commands.",
        ),
        CaptureSpec(
            section="Infrastructure Commands",
            title="Virtualization Help",
            argv=["virtualization", "--help"],
            notes="Cluster, VM, storage, snapshot, and backup sync commands.",
        ),
        CaptureSpec(
            section="Infrastructure Commands",
            title="Virtualization Storage Create Help",
            argv=["virtualization", "storage-create", "--help"],
            notes="Sync Proxmox storage definitions into NetBox.",
        ),
        CaptureSpec(
            section="Infrastructure Commands",
            title="Virtualization Backups Sync Help",
            argv=["virtualization", "vms", "backups-sync-all", "--help"],
            notes="Long-running VM backup synchronization command.",
        ),
        CaptureSpec(
            section="Infrastructure Commands",
            title="Virtualization Snapshots Sync Help",
            argv=["virtualization", "vms", "snapshots-sync-all", "--help"],
            notes="Long-running VM snapshot synchronization command.",
        ),
        CaptureSpec(
            section="Infrastructure Commands",
            title="Extras Help",
            argv=["extras", "--help"],
            notes="Custom-field initialization and related helper commands.",
        ),
    ]
