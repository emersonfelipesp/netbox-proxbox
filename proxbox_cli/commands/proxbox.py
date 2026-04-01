"""CLI commands for /proxbox plugin-config endpoints."""

from __future__ import annotations

from typing import Annotated

import typer

from proxbox_cli.runtime import _get_client
from proxbox_cli.support import print_response, run_with_spinner

proxbox_app = typer.Typer(
    no_args_is_help=True,
    help="Proxbox plugin and backend info commands.",
)

JsonFlag = Annotated[bool, typer.Option("--json", help="Output raw JSON.")]
YamlFlag = Annotated[bool, typer.Option("--yaml", help="Output YAML.")]


@proxbox_app.command("settings")
def proxbox_settings(
    as_json: JsonFlag = False,
    as_yaml: YamlFlag = False,
) -> None:
    """Show resolved Proxbox plugin configuration from NetBox."""
    resp = run_with_spinner(_get_client().get("/proxbox/settings"))
    print_response(resp, as_json=as_json, as_yaml=as_yaml)


@proxbox_app.command("plugins-config")
def proxbox_plugins_config(
    list_all: Annotated[
        bool, typer.Option("--all", help="Return full PLUGINS_CONFIG (all plugins).")
    ] = False,
    as_json: JsonFlag = False,
    as_yaml: YamlFlag = False,
) -> None:
    """Show plugin configuration from NetBox PLUGINS_CONFIG."""
    query = {"list_all": "true"} if list_all else None
    resp = run_with_spinner(
        _get_client().get("/proxbox/netbox/plugins-config", query=query)
    )
    print_response(resp, as_json=as_json, as_yaml=as_yaml)


@proxbox_app.command("default-settings")
def proxbox_default_settings(
    as_json: JsonFlag = False,
    as_yaml: YamlFlag = False,
) -> None:
    """Show Proxbox default settings from the NetBox plugin config."""
    resp = run_with_spinner(_get_client().get("/proxbox/netbox/default-settings"))
    print_response(resp, as_json=as_json, as_yaml=as_yaml)
