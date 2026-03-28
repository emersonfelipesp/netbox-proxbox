"""CLI commands for /proxmox endpoints."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from proxbox_cli.runtime import _get_client
from proxbox_cli.support import load_json_payload, print_response, run_with_spinner

proxmox_app = typer.Typer(no_args_is_help=True, help="Proxmox integration commands.")

# Nested sub-apps
endpoints_app = typer.Typer(no_args_is_help=True, help="Proxmox endpoint CRUD (local DB).")
viewer_app = typer.Typer(no_args_is_help=True, help="Proxmox API codegen and viewer commands.")
cluster_app = typer.Typer(no_args_is_help=True, help="Proxmox cluster commands.")
nodes_app = typer.Typer(no_args_is_help=True, help="Proxmox node commands.")

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
    vmid: Annotated[Optional[str], typer.Option("--vmid", help="Filter by VM ID.")] = None,
    content: Annotated[Optional[str], typer.Option("--content", help="Filter by content type.")] = None,
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
    path: Annotated[str, typer.Argument(help="Top-level Proxmox path (access/cluster/nodes/storage/version).")],
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
    resp = run_with_spinner(_get_client().get(f"/proxmox/{node}/{vm_type}/{vmid}/config"))
    print_response(resp, as_json=as_json, as_yaml=as_yaml)


# ── Proxmox Endpoints CRUD ────────────────────────────────────────────────────

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
    body_json: Annotated[Optional[str], typer.Option("--body-json", help="JSON payload string.")] = None,
    body_file: Annotated[Optional[Path], typer.Option("--body-file", help="Path to JSON payload file.")] = None,
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
    body_json: Annotated[Optional[str], typer.Option("--body-json", help="JSON payload string.")] = None,
    body_file: Annotated[Optional[Path], typer.Option("--body-file", help="Path to JSON payload file.")] = None,
    as_json: JsonFlag = False,
    as_yaml: YamlFlag = False,
) -> None:
    """Update a Proxmox endpoint record."""
    payload = load_json_payload(body_json, body_file)
    resp = run_with_spinner(_get_client().put(f"/proxmox/endpoints/{endpoint_id}", payload=payload))
    print_response(resp, as_json=as_json, as_yaml=as_yaml)


@endpoints_app.command("delete")
def pxendpoint_delete(
    endpoint_id: Annotated[int, typer.Argument(help="Proxmox endpoint ID.")],
    confirm: Annotated[bool, typer.Option("--confirm", help="Skip confirmation prompt.")] = False,
) -> None:
    """Delete a Proxmox endpoint record."""
    if not confirm:
        typer.confirm(f"Delete Proxmox endpoint {endpoint_id}?", abort=True)
    resp = run_with_spinner(_get_client().delete(f"/proxmox/endpoints/{endpoint_id}"))
    print_response(resp)


# ── Viewer / Codegen ──────────────────────────────────────────────────────────

@viewer_app.command("generate")
def viewer_generate(
    body_json: Annotated[Optional[str], typer.Option("--body-json", help="JSON config string.")] = None,
    body_file: Annotated[Optional[Path], typer.Option("--body-file", help="Path to JSON config file.")] = None,
    as_json: JsonFlag = False,
    as_yaml: YamlFlag = False,
) -> None:
    """Run the Proxmox API Viewer crawl and code generation pipeline."""
    payload = load_json_payload(body_json, body_file)
    resp = run_with_spinner(_get_client().post("/proxmox/viewer/generate", payload=payload))
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


# ── Cluster ───────────────────────────────────────────────────────────────────

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
    resource_type: Annotated[Optional[str], typer.Option("--type", help="Filter: vm, storage, node, sdn.")] = None,
    as_json: JsonFlag = False,
    as_yaml: YamlFlag = False,
) -> None:
    """Get cluster resources, optionally filtered by type."""
    query = {"type": resource_type} if resource_type else None
    resp = run_with_spinner(_get_client().get("/proxmox/cluster/resources", query=query))
    print_response(resp, as_json=as_json, as_yaml=as_yaml)


# ── Nodes ─────────────────────────────────────────────────────────────────────

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
    interface_type: Annotated[Optional[str], typer.Option("--type", help="Filter by interface type.")] = None,
    as_json: JsonFlag = False,
    as_yaml: YamlFlag = False,
) -> None:
    """Get network interfaces for a node."""
    query = {"type": interface_type} if interface_type else None
    resp = run_with_spinner(_get_client().get(f"/proxmox/nodes/{node}/network", query=query))
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
