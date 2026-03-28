"""CLI commands for /extras endpoints."""

from __future__ import annotations

from typing import Annotated

import typer

from proxbox_cli.runtime import _get_client
from proxbox_cli.support import print_response, run_with_spinner

extras_app = typer.Typer(no_args_is_help=True, help="Extras commands (custom fields, etc.).")

JsonFlag = Annotated[bool, typer.Option("--json", help="Output raw JSON.")]
YamlFlag = Annotated[bool, typer.Option("--yaml", help="Output YAML.")]


@extras_app.command("custom-fields-create")
def custom_fields_create(
    as_json: JsonFlag = False,
    as_yaml: YamlFlag = False,
) -> None:
    """Create predefined Proxbox custom fields in NetBox (proxmox_vm_id, start_at_boot, etc.)."""
    resp = run_with_spinner(_get_client().get("/extras/extras/custom-fields/create"))
    print_response(resp, as_json=as_json, as_yaml=as_yaml)
