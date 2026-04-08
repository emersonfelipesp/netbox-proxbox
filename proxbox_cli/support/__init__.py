"""Shared CLI helpers: async bridge, output formatting, error handling."""

from __future__ import annotations

from proxbox_cli.support.async_bridge import T, run_with_spinner
from proxbox_cli.support.console import console, stderr
from proxbox_cli.support.output import (
    OUTPUT_FORMAT_CONFLICT_MESSAGE,
    OutputFormat,
    emit_cli_error,
    load_json_payload,
    print_response,
    resolve_output_format,
)
from proxbox_cli.support.tables import (
    _cell,
    _humanize,
    _select_columns,
    render_detail_table,
    render_list_table,
    render_table,
)

__all__ = [
    "OUTPUT_FORMAT_CONFLICT_MESSAGE",
    "OutputFormat",
    "T",
    "console",
    "emit_cli_error",
    "load_json_payload",
    "print_response",
    "render_detail_table",
    "render_list_table",
    "render_table",
    "resolve_output_format",
    "run_with_spinner",
    "stderr",
]
