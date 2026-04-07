"""Proxmox endpoint CRUD and viewer/codegen commands."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from proxbox_cli.runtime import _get_client
from proxbox_cli.support import load_json_payload, print_response, run_with_spinner

endpoints_app = typer.Typer(
    no_args_is_help=True, help="Proxmox endpoint CRUD (local DB)."
)
viewer_app = typer.Typer(
    no_args_is_help=True, help="Proxmox API codegen and viewer commands."
)

JsonFlag = Annotated[bool, typer.Option("--json", help="Output raw JSON.")]
YamlFlag = Annotated[bool, typer.Option("--yaml", help="Output YAML.")]


# ── Endpoints CRUD ──────────────────────────────────────────────────────────────


@endpoints_app.command("list")
def pxendpoint_list(
    as_json: JsonFlag = False,
    as_yaml: YamlFlag = False,
) -> None:
    """List Proxmox endpoint records."""
    resp = run_with_spinner(_get_client().get("/proxmox/endpoints"))
    print_response(resp, as_json=as_json, as_yaml=as_yaml)


@endpoints_app.command("get")
def pxendpoint_get(
    endpoint_id: Annotated[int, typer.Argument(help="Proxmox endpoint ID.")],
    as_json: JsonFlag = False,
    as_yaml: YamlFlag = False,
) -> None:
    """Get a single Proxmox endpoint by ID."""
    resp = run_with_spinner(_get_client().get(f"/proxmox/endpoints/{endpoint_id}"))
    print_response(resp, as_json=as_json, as_yaml=as_yaml)


@endpoints_app.command("create")
def pxendpoint_create(
    body_json: Annotated[
        Optional[str], typer.Option("--body-json", help="JSON payload string.")
    ] = None,
    body_file: Annotated[
        Optional[Path], typer.Option("--body-file", help="Path to JSON payload file.")
    ] = None,
    as_json: JsonFlag = False,
    as_yaml: YamlFlag = False,
) -> None:
    """Create a Proxmox endpoint record."""
    payload = load_json_payload(body_json, body_file)
    resp = run_with_spinner(_get_client().post("/proxmox/endpoints", payload=payload))
    print_response(resp, as_json=as_json, as_yaml=as_yaml)


@endpoints_app.command("update")
def pxendpoint_update(
    endpoint_id: Annotated[int, typer.Argument(help="Proxmox endpoint ID.")],
    body_json: Annotated[
        Optional[str], typer.Option("--body-json", help="JSON payload string.")
    ] = None,
    body_file: Annotated[
        Optional[Path], typer.Option("--body-file", help="Path to JSON payload file.")
    ] = None,
    as_json: JsonFlag = False,
    as_yaml: YamlFlag = False,
) -> None:
    """Update a Proxmox endpoint record."""
    payload = load_json_payload(body_json, body_file)
    resp = run_with_spinner(
        _get_client().put(f"/proxmox/endpoints/{endpoint_id}", payload=payload)
    )
    print_response(resp, as_json=as_json, as_yaml=as_yaml)


@endpoints_app.command("delete")
def pxendpoint_delete(
    endpoint_id: Annotated[int, typer.Argument(help="Proxmox endpoint ID.")],
    confirm: Annotated[
        bool, typer.Option("--confirm", help="Skip confirmation prompt.")
    ] = False,
) -> None:
    """Delete a Proxmox endpoint record."""
    if not confirm:
        typer.confirm(f"Delete Proxmox endpoint {endpoint_id}?", abort=True)
    resp = run_with_spinner(_get_client().delete(f"/proxmox/endpoints/{endpoint_id}"))
    print_response(resp)


# ── Viewer / Codegen ────────────────────────────────────────────────────────────


@viewer_app.command("generate")
def viewer_generate(
    body_json: Annotated[
        Optional[str], typer.Option("--body-json", help="JSON config string.")
    ] = None,
    body_file: Annotated[
        Optional[Path], typer.Option("--body-file", help="Path to JSON config file.")
    ] = None,
    as_json: JsonFlag = False,
    as_yaml: YamlFlag = False,
) -> None:
    """Run the Proxmox API Viewer crawl and code generation pipeline."""
    payload = load_json_payload(body_json, body_file)
    resp = run_with_spinner(
        _get_client().post("/proxmox/viewer/generate", payload=payload)
    )
    print_response(resp, as_json=as_json, as_yaml=as_yaml)


@viewer_app.command("openapi")
def viewer_openapi(
    as_json: JsonFlag = False,
    as_yaml: YamlFlag = False,
) -> None:
    """Return the generated Proxmox OpenAPI schema."""
    resp = run_with_spinner(_get_client().get("/proxmox/viewer/openapi"))
    print_response(resp, as_json=as_json, as_yaml=as_yaml)


@viewer_app.command("openapi-embedded")
def viewer_openapi_embedded(
    as_json: JsonFlag = False,
    as_yaml: YamlFlag = False,
) -> None:
    """Return the Proxmox OpenAPI as embedded in the FastAPI custom schema."""
    resp = run_with_spinner(_get_client().get("/proxmox/viewer/openapi/embedded"))
    print_response(resp, as_json=as_json, as_yaml=as_yaml)


@viewer_app.command("contracts")
def viewer_contracts(
    as_json: JsonFlag = False,
    as_yaml: YamlFlag = False,
) -> None:
    """Report Proxmox and NetBox schema contract diagnostics."""
    resp = run_with_spinner(_get_client().get("/proxmox/viewer/integration/contracts"))
    print_response(resp, as_json=as_json, as_yaml=as_yaml)


@viewer_app.command("pydantic")
def viewer_pydantic() -> None:
    """Print the generated Pydantic v2 model source code."""
    from proxbox_cli.support import console

    resp = run_with_spinner(_get_client().get("/proxmox/viewer/pydantic"))
    console.print(f"Status: {resp.status}")
    console.print(resp.text)
