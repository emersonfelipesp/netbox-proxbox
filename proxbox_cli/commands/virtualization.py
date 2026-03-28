"""CLI commands for /virtualization endpoints."""

from __future__ import annotations

from typing import Annotated, Optional

import typer

from proxbox_cli.runtime import _get_client
from proxbox_cli.support import print_response, run_with_spinner

virtualization_app = typer.Typer(no_args_is_help=True, help="Virtualization commands.")
vms_app = typer.Typer(no_args_is_help=True, help="Virtual machine commands.")
virtualization_app.add_typer(vms_app, name="vms")

JsonFlag = Annotated[bool, typer.Option("--json", help="Output raw JSON.")]
YamlFlag = Annotated[bool, typer.Option("--yaml", help="Output YAML.")]


# ── Top-level virtualization commands ─────────────────────────────────────────

@virtualization_app.command("cluster-types-create")
def cluster_types_create(
    as_json: JsonFlag = False,
    as_yaml: YamlFlag = False,
) -> None:
    """Create cluster types in NetBox."""
    resp = run_with_spinner(_get_client().get("/virtualization/cluster-types/create"))
    print_response(resp, as_json=as_json, as_yaml=as_yaml)


@virtualization_app.command("clusters-create")
def clusters_create(
    as_json: JsonFlag = False,
    as_yaml: YamlFlag = False,
) -> None:
    """Create clusters in NetBox."""
    resp = run_with_spinner(_get_client().get("/virtualization/clusters/create"))
    print_response(resp, as_json=as_json, as_yaml=as_yaml)


# ── Virtual Machine commands ──────────────────────────────────────────────────

@vms_app.command("list")
def vms_list(
    as_json: JsonFlag = False,
    as_yaml: YamlFlag = False,
) -> None:
    """List all virtual machines from NetBox."""
    resp = run_with_spinner(_get_client().get("/virtualization/virtual-machines/"))
    print_response(resp, as_json=as_json, as_yaml=as_yaml)


@vms_app.command("get")
def vms_get(
    vm_id: Annotated[int, typer.Argument(help="VM ID.")],
    as_json: JsonFlag = False,
    as_yaml: YamlFlag = False,
) -> None:
    """Get a single VM by ID."""
    resp = run_with_spinner(_get_client().get(f"/virtualization/virtual-machines/{vm_id}"))
    print_response(resp, as_json=as_json, as_yaml=as_yaml)


@vms_app.command("create")
def vms_create(
    as_json: JsonFlag = False,
    as_yaml: YamlFlag = False,
) -> None:
    """Sync VMs from Proxmox to NetBox (creates VMs, interfaces, IPs). [NOTE: triggers full sync]"""
    resp = run_with_spinner(_get_client().get("/virtualization/virtual-machines/create"))
    print_response(resp, as_json=as_json, as_yaml=as_yaml)


@vms_app.command("create-test")
def vms_create_test(
    as_json: JsonFlag = False,
    as_yaml: YamlFlag = False,
) -> None:
    """Create a hardcoded test VM in NetBox."""
    resp = run_with_spinner(_get_client().get("/virtualization/virtual-machines/create-test"))
    print_response(resp, as_json=as_json, as_yaml=as_yaml)


@vms_app.command("summary-example")
def vms_summary_example(
    as_json: JsonFlag = False,
    as_yaml: YamlFlag = False,
) -> None:
    """Return an example VirtualMachineSummary response."""
    resp = run_with_spinner(_get_client().get("/virtualization/virtual-machines/summary/example"))
    print_response(resp, as_json=as_json, as_yaml=as_yaml)


@vms_app.command("summary")
def vms_summary(
    vm_id: Annotated[int, typer.Argument(help="VM ID.")],
    as_json: JsonFlag = False,
    as_yaml: YamlFlag = False,
) -> None:
    """Get summary for a specific VM by ID."""
    resp = run_with_spinner(_get_client().get(f"/virtualization/virtual-machines/{vm_id}/summary"))
    print_response(resp, as_json=as_json, as_yaml=as_yaml)


@vms_app.command("interfaces-create")
def vms_interfaces_create(
    as_json: JsonFlag = False,
    as_yaml: YamlFlag = False,
) -> None:
    """Create VM interfaces in NetBox. [NOTE: triggers sync]"""
    resp = run_with_spinner(_get_client().get("/virtualization/virtual-machines/interfaces/create"))
    print_response(resp, as_json=as_json, as_yaml=as_yaml)


@vms_app.command("ip-address-create")
def vms_ip_address_create(
    as_json: JsonFlag = False,
    as_yaml: YamlFlag = False,
) -> None:
    """Create IP addresses for VM interfaces in NetBox. [NOTE: triggers sync]"""
    resp = run_with_spinner(
        _get_client().get("/virtualization/virtual-machines/interfaces/ip-address/create")
    )
    print_response(resp, as_json=as_json, as_yaml=as_yaml)


@vms_app.command("disks-create")
def vms_disks_create(
    as_json: JsonFlag = False,
    as_yaml: YamlFlag = False,
) -> None:
    """Create virtual disks for VMs in NetBox. [NOTE: triggers sync]"""
    resp = run_with_spinner(
        _get_client().get("/virtualization/virtual-machines/virtual-disks/create")
    )
    print_response(resp, as_json=as_json, as_yaml=as_yaml)


@vms_app.command("backups-create")
def vms_backups_create(
    node: Annotated[Optional[str], typer.Option("--node", help="Node name.")] = None,
    storage: Annotated[Optional[str], typer.Option("--storage", help="Storage ID.")] = None,
    vmid: Annotated[Optional[str], typer.Option("--vmid", help="VM ID filter.")] = None,
    as_json: JsonFlag = False,
    as_yaml: YamlFlag = False,
) -> None:
    """Create backups for a specific node/storage. [NOTE: triggers sync]"""
    query: dict = {}
    if node:
        query["node"] = node
    if storage:
        query["storage"] = storage
    if vmid:
        query["vmid"] = vmid
    resp = run_with_spinner(
        _get_client().get(
            "/virtualization/virtual-machines/backups/create",
            query=query or None,
        )
    )
    print_response(resp, as_json=as_json, as_yaml=as_yaml)


@vms_app.command("backups-sync-all")
def vms_backups_sync_all(
    delete_stale: Annotated[bool, typer.Option("--delete-stale", help="Delete stale backup records.")] = False,
    as_json: JsonFlag = False,
    as_yaml: YamlFlag = False,
) -> None:
    """Sync ALL backups across all clusters/nodes/storages. [NOTE: long-running sync]"""
    query = {"delete_stale": "true"} if delete_stale else None
    resp = run_with_spinner(
        _get_client().get("/virtualization/virtual-machines/backups/all/create", query=query)
    )
    print_response(resp, as_json=as_json, as_yaml=as_yaml)


@vms_app.command("journal-test")
def vms_journal_test(
    as_json: JsonFlag = False,
    as_yaml: YamlFlag = False,
) -> None:
    """Test endpoint: creates sync process and journal entries."""
    resp = run_with_spinner(
        _get_client().get(
            "/virtualization/virtual-machines/sync-process/journal-entry/test/create"
        )
    )
    print_response(resp, as_json=as_json, as_yaml=as_yaml)
