"""CLI commands for /proxmox endpoints."""

from __future__ import annotations

from typing import Annotated, Optional

import typer

from proxbox_cli.commands.proxmox_cluster import cluster_app
from proxbox_cli.commands.proxmox_endpoints import endpoints_app, viewer_app
from proxbox_cli.commands.proxmox_nodes import nodes_app
from proxbox_cli.runtime import _get_client
from proxbox_cli.support import print_response, run_with_spinner

proxmox_app = typer.Typer(no_args_is_help=True, help="Proxmox integration commands.")

proxmox_app.add_typer(endpoints_app, name="endpoints")
proxmox_app.add_typer(viewer_app, name="viewer")
proxmox_app.add_typer(cluster_app, name="cluster")
proxmox_app.add_typer(nodes_app, name="nodes")

# ── Common flags ──────────────────────────────────────────────────────────────

JsonFlag = Annotated[bool, typer.Option("--json", help="Output raw JSON.")]
YamlFlag = Annotated[bool, typer.Option("--yaml", help="Output YAML.")]


# ── Direct proxmox commands ───────────────────────────────────────────────────


@proxmox_app.command()
def overview(
    as_json: JsonFlag = False,
    as_yaml: YamlFlag = False,
) -> None:
    """Show Proxmox overview (access, cluster, nodes, pools, storage, version)."""
    resp = run_with_spinner(_get_client().get("/proxmox/"))
    print_response(resp, as_json=as_json, as_yaml=as_yaml)


@proxmox_app.command()
def sessions(
    as_json: JsonFlag = False,
    as_yaml: YamlFlag = False,
) -> None:
    """List all active Proxmox sessions."""
    resp = run_with_spinner(_get_client().get("/proxmox/sessions"))
    print_response(resp, as_json=as_json, as_yaml=as_yaml)


@proxmox_app.command()
def version(
    as_json: JsonFlag = False,
    as_yaml: YamlFlag = False,
) -> None:
    """Get Proxmox version from all connected sessions."""
    resp = run_with_spinner(_get_client().get("/proxmox/version"))
    print_response(resp, as_json=as_json, as_yaml=as_yaml)


@proxmox_app.command()
def storage(
    as_json: JsonFlag = False,
    as_yaml: YamlFlag = False,
) -> None:
    """Get storage info from all Proxmox sessions."""
    resp = run_with_spinner(_get_client().get("/proxmox/storage"))
    print_response(resp, as_json=as_json, as_yaml=as_yaml)


@proxmox_app.command("storage-content")
def storage_content(
    node: Annotated[str, typer.Argument(help="Node name.")],
    storage_id: Annotated[str, typer.Argument(help="Storage ID.")],
    vmid: Annotated[
        Optional[str], typer.Option("--vmid", help="Filter by VM ID.")
    ] = None,
    content: Annotated[
        Optional[str], typer.Option("--content", help="Filter by content type.")
    ] = None,
    as_json: JsonFlag = False,
    as_yaml: YamlFlag = False,
) -> None:
    """Get storage content (backups, images) for a node and storage."""
    query: dict = {}
    if vmid:
        query["vmid"] = vmid
    if content:
        query["content"] = content
    resp = run_with_spinner(
        _get_client().get(
            f"/proxmox/nodes/{node}/storage/{storage_id}/content",
            query=query or None,
        )
    )
    print_response(resp, as_json=as_json, as_yaml=as_yaml)


@proxmox_app.command("top-level")
def top_level(
    path: Annotated[
        str,
        typer.Argument(
            help="Top-level Proxmox path (access/cluster/nodes/storage/version)."
        ),
    ],
    as_json: JsonFlag = False,
    as_yaml: YamlFlag = False,
) -> None:
    """Query a dynamic top-level Proxmox path."""
    resp = run_with_spinner(_get_client().get(f"/proxmox/{path}"))
    print_response(resp, as_json=as_json, as_yaml=as_yaml)


@proxmox_app.command("vm-config")
def vm_config(
    node: Annotated[str, typer.Argument(help="Node name.")],
    vm_type: Annotated[str, typer.Argument(help="VM type: qemu or lxc.")],
    vmid: Annotated[str, typer.Argument(help="VM ID.")],
    as_json: JsonFlag = False,
    as_yaml: YamlFlag = False,
) -> None:
    """Get VM config for a specific VM."""
    resp = run_with_spinner(
        _get_client().get(f"/proxmox/{node}/{vm_type}/{vmid}/config")
    )
    print_response(resp, as_json=as_json, as_yaml=as_yaml)
