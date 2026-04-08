"""Output formatting, error helpers, and payload loading."""

from __future__ import annotations

import json
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from proxbox_cli.client import JSONValue
from proxbox_cli.support.console import console, stderr
from proxbox_cli.support.tables import render_table

if TYPE_CHECKING:
    from proxbox_cli.client import ApiResponse

OUTPUT_FORMAT_CONFLICT_MESSAGE = (
    "Options --json and --yaml are mutually exclusive; pick one."
)


class OutputFormat(StrEnum):
    """OutputFormat implementation."""

    HUMAN = "human"
    JSON = "json"
    YAML = "yaml"


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
