"""CLI commands for /netbox endpoints."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from proxbox_cli.runtime import _get_client
from proxbox_cli.support import load_json_payload, print_response, run_with_spinner

netbox_app = typer.Typer(no_args_is_help=True, help="NetBox integration commands.")
endpoint_app = typer.Typer(no_args_is_help=True, help="NetBox endpoint CRUD.")
netbox_app.add_typer(endpoint_app, name="endpoint")

# ── Common flags ──────────────────────────────────────────────────────────────

JsonFlag = Annotated[bool, typer.Option("--json", help="Output raw JSON.")]
YamlFlag = Annotated[bool, typer.Option("--yaml", help="Output YAML.")]


# ── Direct commands ───────────────────────────────────────────────────────────


@netbox_app.command()
def status(
    as_json: JsonFlag = False,
    as_yaml: YamlFlag = False,
) -> None:
    """Show NetBox API status."""
    resp = run_with_spinner(_get_client().get("/netbox/status"))
    print_response(resp, as_json=as_json, as_yaml=as_yaml)


@netbox_app.command()
def openapi(
    as_json: JsonFlag = False,
    as_yaml: YamlFlag = False,
) -> None:
    """Fetch the NetBox OpenAPI schema."""
    resp = run_with_spinner(_get_client().get("/netbox/openapi"))
    print_response(resp, as_json=as_json, as_yaml=as_yaml)


# ── Endpoint CRUD ─────────────────────────────────────────────────────────────


@endpoint_app.command("list")
def endpoint_list(
    as_json: JsonFlag = False,
    as_yaml: YamlFlag = False,
) -> None:
    """List NetBox endpoint records."""
    resp = run_with_spinner(_get_client().get("/netbox/endpoint"))
    print_response(resp, as_json=as_json, as_yaml=as_yaml)


@endpoint_app.command("get")
def endpoint_get(
    netbox_id: Annotated[int, typer.Argument(help="NetBox endpoint ID.")],
    as_json: JsonFlag = False,
    as_yaml: YamlFlag = False,
) -> None:
    """Get a single NetBox endpoint by ID."""
    resp = run_with_spinner(_get_client().get(f"/netbox/endpoint/{netbox_id}"))
    print_response(resp, as_json=as_json, as_yaml=as_yaml)


@endpoint_app.command("create")
def endpoint_create(
    body_json: Annotated[
        str | None, typer.Option("--body-json", help="JSON payload string.")
    ] = None,
    body_file: Annotated[
        Path | None, typer.Option("--body-file", help="Path to JSON payload file.")
    ] = None,
    as_json: JsonFlag = False,
    as_yaml: YamlFlag = False,
) -> None:
    """Create a NetBox endpoint record."""
    payload = load_json_payload(body_json, body_file)
    resp = run_with_spinner(_get_client().post("/netbox/endpoint", payload=payload))
    print_response(resp, as_json=as_json, as_yaml=as_yaml)


@endpoint_app.command("update")
def endpoint_update(
    netbox_id: Annotated[int, typer.Argument(help="NetBox endpoint ID.")],
    body_json: Annotated[
        str | None, typer.Option("--body-json", help="JSON payload string.")
    ] = None,
    body_file: Annotated[
        Path | None, typer.Option("--body-file", help="Path to JSON payload file.")
    ] = None,
    as_json: JsonFlag = False,
    as_yaml: YamlFlag = False,
) -> None:
    """Update a NetBox endpoint record."""
    payload = load_json_payload(body_json, body_file)
    resp = run_with_spinner(
        _get_client().put(f"/netbox/endpoint/{netbox_id}", payload=payload)
    )
    print_response(resp, as_json=as_json, as_yaml=as_yaml)


@endpoint_app.command("delete")
def endpoint_delete(
    netbox_id: Annotated[int, typer.Argument(help="NetBox endpoint ID.")],
    confirm: Annotated[
        bool, typer.Option("--confirm", help="Skip confirmation prompt.")
    ] = False,
) -> None:
    """Delete a NetBox endpoint record."""
    if not confirm:
        typer.confirm(f"Delete NetBox endpoint {netbox_id}?", abort=True)
    resp = run_with_spinner(_get_client().delete(f"/netbox/endpoint/{netbox_id}"))
    print_response(resp)
