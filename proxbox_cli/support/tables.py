"""Table rendering helpers for CLI output."""

from __future__ import annotations

import json
from typing import cast

from rich.table import Table

from proxbox_cli.client import JSONValue
from proxbox_cli.support.console import console

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


def render_table(parsed: JSONValue) -> None:
    """Render table."""
    if isinstance(parsed, list):
        if all(isinstance(item, dict) for item in parsed):
            render_list_table(cast(list[dict[str, JSONValue]], parsed))
        else:
            console.print(parsed)
    elif isinstance(parsed, dict):
        results = parsed.get("results")
        if isinstance(results, list) and all(
            isinstance(item, dict) for item in results
        ):
            count = parsed.get("count")
            render_list_table(
                cast(list[dict[str, JSONValue]], results),
                count=count if isinstance(count, int) else None,
            )
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


def render_list_table(
    rows: list[dict[str, JSONValue]], *, count: int | None = None
) -> None:
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
