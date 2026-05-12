"""Proxbox CLI — Typer entrypoint and root commands."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

try:
    import click
    import typer
except ModuleNotFoundError as exc:
    missing = exc.name or ""
    if missing in {"click", "typer"}:
        raise ModuleNotFoundError(
            "proxbox_cli requires CLI dependencies. Install with: pip install 'netbox-proxbox[cli]'"
        ) from exc
    raise

from rich.console import Console

from proxbox_cli.commands.dcim import dcim_app
from proxbox_cli.commands.extras import extras_app
from proxbox_cli.commands.netbox import netbox_app
from proxbox_cli.commands.proxmox import proxmox_app
from proxbox_cli.commands.proxbox import proxbox_app
from proxbox_cli.commands.sync import sync_app
from proxbox_cli.commands.virtualization import virtualization_app
from proxbox_cli.config import Config, load_config, normalize_base_url, save_config
from proxbox_cli.runtime import _cache_config, _ensure_config, _get_client
from proxbox_cli.support import (
    console,
    emit_cli_error,
    print_response,
    run_with_spinner,
)

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Proxbox CLI — interact with the proxbox-api backend.",
)

# Wire sub-apps
app.add_typer(netbox_app, name="netbox")
app.add_typer(proxmox_app, name="proxmox")
app.add_typer(proxbox_app, name="proxbox")
app.add_typer(dcim_app, name="dcim")
app.add_typer(virtualization_app, name="virtualization")
app.add_typer(extras_app, name="extras")
app.add_typer(sync_app, name="sync")

docs_app = typer.Typer(no_args_is_help=True, help="Documentation generation commands.")
app.add_typer(docs_app, name="docs")


# ── Root commands ─────────────────────────────────────────────────────────────


@app.command()
def init() -> None:
    """Interactively configure the proxbox-api base URL."""
    existing = load_config()
    console.print(f"Current base URL: [bold]{existing.base_url}[/bold]")
    raw = typer.prompt("proxbox-api base URL", default=existing.base_url)
    timeout_str = typer.prompt(
        "Request timeout (seconds)", default=str(existing.timeout)
    )

    try:
        timeout = float(timeout_str)
    except ValueError:
        emit_cli_error(f"Invalid timeout value: {timeout_str!r}")

    cfg = Config(base_url=normalize_base_url(raw), timeout=timeout)
    save_config(cfg)
    _cache_config(cfg)
    console.print(f"[green]Config saved.[/green] Base URL: {cfg.base_url}")


@app.command("config")
def show_config() -> None:
    """Show the current CLI configuration."""
    cfg = _ensure_config()
    console.print(f"Base URL : [bold]{cfg.base_url}[/bold]")
    console.print(f"Timeout  : {cfg.timeout}s")


@app.command()
def test() -> None:
    """Test connectivity to the proxbox-api server."""
    cfg = _ensure_config()
    console.print(f"Testing connection to [bold]{cfg.base_url}[/bold] ...")
    resp = run_with_spinner(_get_client().get("/"))
    if resp.is_ok():
        console.print("[green]Connection OK[/green]")
    else:
        console.print(f"[red]Connection failed (HTTP {resp.status})[/red]")
    print_response(resp, as_json=False)


@app.command("version")
def show_version(
    as_json: Annotated[bool, typer.Option("--json", help="Output raw JSON.")] = False,
    as_yaml: Annotated[bool, typer.Option("--yaml", help="Output YAML.")] = False,
) -> None:
    """Show the proxbox-api backend version."""
    resp = run_with_spinner(_get_client().get("/version"))
    print_response(resp, as_json=as_json, as_yaml=as_yaml)


@app.command()
def info(
    as_json: Annotated[bool, typer.Option("--json", help="Output raw JSON.")] = False,
    as_yaml: Annotated[bool, typer.Option("--yaml", help="Output YAML.")] = False,
) -> None:
    """Show proxbox-api project info."""
    resp = run_with_spinner(_get_client().get("/"))
    print_response(resp, as_json=as_json, as_yaml=as_yaml)


@app.command()
def cache(
    as_json: Annotated[bool, typer.Option("--json", help="Output raw JSON.")] = False,
    as_yaml: Annotated[bool, typer.Option("--yaml", help="Output YAML.")] = False,
) -> None:
    """Show the in-memory cache contents."""
    resp = run_with_spinner(_get_client().get("/cache"))
    print_response(resp, as_json=as_json, as_yaml=as_yaml)


@app.command("clear-cache")
def clear_cache() -> None:
    """Clear the in-memory cache on the proxbox-api server."""
    resp = run_with_spinner(_get_client().get("/clear-cache"))
    print_response(resp)


@app.command("full-update")
def full_update(
    as_json: Annotated[bool, typer.Option("--json", help="Output raw JSON.")] = False,
    as_yaml: Annotated[bool, typer.Option("--yaml", help="Output YAML.")] = False,
) -> None:
    """Run a full sync: creates devices (nodes) then VMs. [NOTE: long-running operation]"""
    console.print("[yellow]Starting full update sync...[/yellow]")
    resp = run_with_spinner(_get_client().get("/full-update"))
    print_response(resp, as_json=as_json, as_yaml=as_yaml)


@docs_app.command("generate-capture")
def docs_generate_capture(
    output: Annotated[
        Optional[str], typer.Option("--output", help="Markdown snapshot output path.")
    ] = None,
    raw_dir: Annotated[
        Optional[str], typer.Option("--raw-dir", help="Raw JSON artifact directory.")
    ] = None,
    catalog_output: Annotated[
        Optional[str],
        typer.Option("--catalog-output", help="Command catalog JSON output path."),
    ] = None,
) -> None:
    """Generate machine-readable CLI docs artifacts for the MkDocs site."""
    from proxbox_cli.docgen_capture import (
        generate_command_capture_docs,
        resolve_capture_paths,
    )

    output_path, raw_dir_path, catalog_path = resolve_capture_paths(
        Path(output) if output else None,
        Path(raw_dir) if raw_dir else None,
        Path(catalog_output) if catalog_output else None,
    )
    raise SystemExit(
        generate_command_capture_docs(
            output=output_path,
            raw_dir=raw_dir_path,
            catalog_output=catalog_path,
        )
    )


# ── Entrypoint ────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    """Run the command entrypoint."""
    command = typer.main.get_command(app)
    try:
        command.main(argv, standalone_mode=False)
        return 0
    except KeyboardInterrupt:
        Console(stderr=True).print("\n[yellow]Aborted.[/yellow]")
        return 130
    except click.Abort:
        Console(stderr=True).print("\n[yellow]Aborted.[/yellow]")
        return 1
    except click.ClickException as exc:
        Console(stderr=True).print(f"[red]Error:[/red] {exc.format_message()}")
        return exc.exit_code
    except SystemExit as exc:
        return int(exc.code) if exc.code is not None else 0
    except Exception as exc:
        Console(stderr=True).print(f"[red]Unexpected error:[/red] {exc}")
        return 1
