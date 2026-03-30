"""CLI commands for /dcim endpoints."""

from __future__ import annotations

from typing import Annotated

import typer

from proxbox_cli.runtime import _get_client
from proxbox_cli.support import print_response, run_with_spinner

dcim_app = typer.Typer(
    no_args_is_help=True, help="DCIM (datacenter infrastructure) commands."
)

JsonFlag = Annotated[bool, typer.Option("--json", help="Output raw JSON.")]
YamlFlag = Annotated[bool, typer.Option("--yaml", help="Output YAML.")]


@dcim_app.command("devices")
def devices(
    as_json: JsonFlag = False,
    as_yaml: YamlFlag = False,
) -> None:
    """List devices."""
    resp = run_with_spinner(_get_client().get("/dcim/devices"))
    print_response(resp, as_json=as_json, as_yaml=as_yaml)


@dcim_app.command("devices-create")
def devices_create(
    as_json: JsonFlag = False,
    as_yaml: YamlFlag = False,
) -> None:
    """Sync Proxmox nodes to NetBox devices. [NOTE: triggers a full node sync]"""
    resp = run_with_spinner(_get_client().get("/dcim/devices/create"))
    print_response(resp, as_json=as_json, as_yaml=as_yaml)


@dcim_app.command("interfaces-create")
def interfaces_create(
    node: Annotated[str, typer.Argument(help="Node name to create interfaces for.")],
    as_json: JsonFlag = False,
    as_yaml: YamlFlag = False,
) -> None:
    """Create interfaces and IPs for a specific node device."""
    resp = run_with_spinner(
        _get_client().get(f"/dcim/devices/{node}/interfaces/create")
    )
    print_response(resp, as_json=as_json, as_yaml=as_yaml)


@dcim_app.command("interfaces-create-all")
def interfaces_create_all(
    as_json: JsonFlag = False,
    as_yaml: YamlFlag = False,
) -> None:
    """Create interfaces for all node devices."""
    resp = run_with_spinner(_get_client().get("/dcim/devices/interfaces/create"))
    print_response(resp, as_json=as_json, as_yaml=as_yaml)
