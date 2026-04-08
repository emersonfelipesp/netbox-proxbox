"""Proxmox cluster commands."""

from __future__ import annotations

from typing import Annotated, Optional

import typer

from proxbox_cli.runtime import _get_client
from proxbox_cli.support import print_response, run_with_spinner

cluster_app = typer.Typer(no_args_is_help=True, help="Proxmox cluster commands.")

JsonFlag = Annotated[bool, typer.Option("--json", help="Output raw JSON.")]
YamlFlag = Annotated[bool, typer.Option("--yaml", help="Output YAML.")]


@cluster_app.command("status")
def cluster_status(
    as_json: JsonFlag = False,
    as_yaml: YamlFlag = False,
) -> None:
    """Get cluster status (name, nodes, quorate, mode)."""
    resp = run_with_spinner(_get_client().get("/proxmox/cluster/status"))
    print_response(resp, as_json=as_json, as_yaml=as_yaml)


@cluster_app.command("resources")
def cluster_resources(
    resource_type: Annotated[
        Optional[str], typer.Option("--type", help="Filter: vm, storage, node, sdn.")
    ] = None,
    as_json: JsonFlag = False,
    as_yaml: YamlFlag = False,
) -> None:
    """Get cluster resources, optionally filtered by type."""
    query = {"type": resource_type} if resource_type else None
    resp = run_with_spinner(
        _get_client().get("/proxmox/cluster/resources", query=query)
    )
    print_response(resp, as_json=as_json, as_yaml=as_yaml)
