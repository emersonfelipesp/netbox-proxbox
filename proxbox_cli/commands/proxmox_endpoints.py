"""Proxmox endpoint CRUD and viewer/codegen commands."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from proxbox_cli.runtime import _get_client
from proxbox_cli.support import (
    load_json_payload,
    print_response,
    print_text_response,
    run_with_spinner,
)

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
        str | None, typer.Option("--body-json", help="JSON payload string.")
    ] = None,
    body_file: Annotated[
        Path | None, typer.Option("--body-file", help="Path to JSON payload file.")
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
        str | None, typer.Option("--body-json", help="JSON payload string.")
    ] = None,
    body_file: Annotated[
        Path | None, typer.Option("--body-file", help="Path to JSON payload file.")
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
    persist: Annotated[bool, typer.Option(help="Persist generated artifacts.")] = True,
    workers: Annotated[int, typer.Option(min=1, max=32)] = 10,
    retry_count: Annotated[int, typer.Option(min=0, max=10)] = 2,
    retry_backoff: Annotated[float, typer.Option(min=0.0, max=5.0)] = 0.35,
    checkpoint_every: Annotated[int, typer.Option(min=1, max=500)] = 50,
    source_url: Annotated[str, typer.Option(help="Proxmox API viewer URL.")] = (
        "https://pve.proxmox.com/pve-docs/api-viewer/"
    ),
    version_tag: Annotated[
        str, typer.Option(help="Generated artifact version tag.")
    ] = "latest",
    as_json: JsonFlag = False,
    as_yaml: YamlFlag = False,
) -> None:
    """Run viewer code generation; the backend must enable runtime code generation."""
    query = {
        "persist": str(persist).lower(),
        "workers": workers,
        "retry_count": retry_count,
        "retry_backoff": retry_backoff,
        "checkpoint_every": checkpoint_every,
        "source_url": source_url,
        "version_tag": version_tag,
    }
    resp = run_with_spinner(_get_client().post("/proxmox/viewer/generate", query=query))
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
    resp = run_with_spinner(_get_client().get("/proxmox/viewer/pydantic"))
    print_text_response(resp)
