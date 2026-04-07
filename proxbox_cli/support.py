"""Shared CLI helpers: async bridge, output formatting, error handling."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Coroutine
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, TypeVar

import yaml
from rich.console import Console
from rich.table import Table

from proxbox_cli.client import JSONValue

if TYPE_CHECKING:
    from proxbox_cli.client import ApiResponse

T = TypeVar("T")

console = Console()
stderr = Console(stderr=True)

# Fields shown by default in list tables (ordered by priority).
_LIST_PRIORITY = [
    "id",
    "name",
    "display",
    "status",
    "type",
    "role",
    "ip_address",
    "domain",
    "port",
    "username",
]

OUTPUT_FORMAT_CONFLICT_MESSAGE = (
    "Options --json and --yaml are mutually exclusive; pick one."
)


class OutputFormat(StrEnum):
    """OutputFormat implementation."""
    HUMAN = "human"
    JSON = "json"
    YAML = "yaml"


def run_with_spinner(coro: Coroutine[object, object, T]) -> T:
    """Bridge an async coroutine to sync with a Rich spinner."""
    with console.status("[bold]Fetching...[/bold]", spinner="dots"):
        return asyncio.run(coro)


def resolve_output_format(*, as_json: bool, as_yaml: bool) -> OutputFormat:
    """Resolve output format."""
    if as_json and as_yaml:
        emit_cli_error(OUTPUT_FORMAT_CONFLICT_MESSAGE)
    if as_json:
        return OutputFormat.JSON
    if as_yaml:
        return OutputFormat.YAML
    return OutputFormat.HUMAN


def emit_cli_error(message: str, *, exit_code: int = 1) -> None:
    """Handle emit cli error."""
    stderr.print(f"[red]Error:[/red] {message}")
    raise SystemExit(exit_code)


def load_json_payload(
    body_json: str | None,
    body_file: Path | None,
) -> JSONValue | None:
    """Parse JSON from an inline string or a file path; raise on conflict."""
    if body_json and body_file:
        emit_cli_error("Use either --body-json or --body-file, not both.")
    if body_json:
        try:
            return json.loads(body_json)
        except json.JSONDecodeError as exc:
            emit_cli_error(f"Invalid JSON in --body-json: {exc}")
    if body_file:
        try:
            return json.loads(body_file.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            emit_cli_error(f"Could not read --body-file: {exc}")
    return None


# ── Output rendering ──────────────────────────────────────────────────────────


def print_response(
    resp: ApiResponse,
    *,
    as_json: bool = False,
    as_yaml: bool = False,
) -> None:
    """Print response."""
    fmt = resolve_output_format(as_json=as_json, as_yaml=as_yaml)
    color = "green" if resp.is_ok() else "red"
    console.print(f"[{color}]Status: {resp.status}[/{color}]")

    try:
        parsed = resp.json_data()
    except (json.JSONDecodeError, ValueError):
        console.print(resp.text)
        return

    if fmt == OutputFormat.JSON:
        console.print(json.dumps(parsed, indent=2, sort_keys=True))
    elif fmt == OutputFormat.YAML:
        console.print(yaml.dump(parsed, allow_unicode=True), end="")
    else:
        render_table(parsed)


def render_table(parsed: JSONValue) -> None:
    """Render table."""
    if isinstance(parsed, list):
        if all(isinstance(item, dict) for item in parsed):
            render_list_table(parsed)
        else:
            console.print(parsed)
    elif isinstance(parsed, dict):
        # NetBox-style paginated list: {"count": N, "results": [...]}
        results = parsed.get("results")
        if isinstance(results, list) and all(isinstance(item, dict) for item in results):
            count = parsed.get("count")
            render_list_table(results, count=count if isinstance(count, int) else None)
        else:
            render_detail_table(parsed)
    else:
        console.print(parsed)


def _select_columns(rows: list[dict[str, JSONValue]]) -> list[str]:
    if not rows:
        return []
    all_keys: list[str] = list(rows[0].keys())
    priority = [k for k in _LIST_PRIORITY if k in all_keys]
    remaining = [k for k in all_keys if k not in priority]
    ordered = priority + remaining
    return ordered[:8]


def render_list_table(rows: list[dict[str, JSONValue]], *, count: int | None = None) -> None:
    """Render list table."""
    if not rows:
        console.print("[dim]No results.[/dim]")
        return

    columns = _select_columns(rows)
    title = f"{count} total" if count is not None else f"{len(rows)} items"
    table = Table(title=title, show_lines=False)
    for col in columns:
        table.add_column(_humanize(col), overflow="fold")
    for row in rows:
        table.add_row(*[_cell(row.get(col)) for col in columns])
    console.print(table)


def render_detail_table(obj: dict[str, JSONValue]) -> None:
    """Render detail table."""
    table = Table(show_header=True, show_lines=True)
    table.add_column("Field")
    table.add_column("Value")
    for key, value in obj.items():
        table.add_row(_humanize(key), _cell(value))
    console.print(table)


def _humanize(field: str) -> str:
    return field.replace("_", " ").title()


def _cell(value: JSONValue) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    return str(value)
