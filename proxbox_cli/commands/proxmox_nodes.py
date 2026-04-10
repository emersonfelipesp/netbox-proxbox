"""Proxmox node commands."""

from __future__ import annotations

from typing import Annotated

import typer

from proxbox_cli.runtime import _get_client
from proxbox_cli.support import print_response, run_with_spinner

nodes_app = typer.Typer(no_args_is_help=True, help="Proxmox node commands.")

JsonFlag = Annotated[bool, typer.Option("--json", help="Output raw JSON.")]
YamlFlag = Annotated[bool, typer.Option("--yaml", help="Output YAML.")]


@nodes_app.command("list")
def nodes_list(
    as_json: JsonFlag = False,
    as_yaml: YamlFlag = False,
) -> None:
    """Get node info (cpu, mem, status, fingerprint) from all sessions."""
    resp = run_with_spinner(_get_client().get("/proxmox/nodes/"))
    print_response(resp, as_json=as_json, as_yaml=as_yaml)


@nodes_app.command("network")
def nodes_network(
    node: Annotated[str, typer.Argument(help="Node name.")],
    interface_type: Annotated[
        str | None, typer.Option("--type", help="Filter by interface type.")
    ] = None,
    as_json: JsonFlag = False,
    as_yaml: YamlFlag = False,
) -> None:
    """Get network interfaces for a node."""
    query = {"type": interface_type} if interface_type else None
    resp = run_with_spinner(
        _get_client().get(f"/proxmox/nodes/{node}/network", query=query)
    )
    print_response(resp, as_json=as_json, as_yaml=as_yaml)


@nodes_app.command("qemu")
def nodes_qemu(
    node: Annotated[str, typer.Argument(help="Node name.")],
    as_json: JsonFlag = False,
    as_yaml: YamlFlag = False,
) -> None:
    """List QEMU VMs on a specific node."""
    resp = run_with_spinner(_get_client().get(f"/proxmox/nodes/{node}/qemu"))
    print_response(resp, as_json=as_json, as_yaml=as_yaml)


@nodes_app.command("lxc")
def nodes_lxc(
    node: Annotated[str, typer.Argument(help="Node name.")],
    as_json: JsonFlag = False,
    as_yaml: YamlFlag = False,
) -> None:
    """List LXC containers on a specific node."""
    resp = run_with_spinner(_get_client().get(f"/proxmox/nodes/{node}/lxc"))
    print_response(resp, as_json=as_json, as_yaml=as_yaml)
