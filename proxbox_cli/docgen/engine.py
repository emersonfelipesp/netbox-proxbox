"""Capture selected help output and build a command catalog for MkDocs."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, TextIO

import typer
from rich.console import Console
from rich.theme import Theme

from proxbox_cli.docgen.models import (
    DEFAULT_CAPTURE_TIMEOUT_SECONDS,
    CaptureResult,
    CaptureSpec,
    build_slug,
)

CAPTURE_WIDTH = 80
_DOCGEN_ENV = "_PROXBOX_CLI_DOCGEN"


class CaptureEngine:
    """Run Proxbox CLI capture specs and persist their artifacts."""

    def __init__(
        self,
        *,
        log: TextIO | None = None,
        timeout_seconds: float = DEFAULT_CAPTURE_TIMEOUT_SECONDS,
    ) -> None:
        self._log = log or sys.stderr
        self._timeout_seconds = timeout_seconds

    def capture_all(self, specs: list[CaptureSpec]) -> list[CaptureResult]:
        """Capture every configured command spec in declaration order."""
        return [self.capture(spec) for spec in specs]

    def capture(self, spec: CaptureSpec) -> CaptureResult:
        """Execute one `python -m proxbox_cli ...` capture."""
        started = time.perf_counter()
        completed = self._execute(spec)
        elapsed = time.perf_counter() - started
        return _capture_result(spec, completed, elapsed)

    def _execute(self, spec: CaptureSpec) -> subprocess.CompletedProcess[str]:
        """Run one bounded documentation capture subprocess."""
        return subprocess.run(
            [sys.executable, "-m", "proxbox_cli", *spec.argv],
            capture_output=True,
            cwd=str(_repo_root()),
            env=_capture_environment(),
            text=True,
            timeout=self._timeout_seconds,
        )

    def write_artifacts(self, results: list[CaptureResult], raw_dir: Path) -> None:
        """Write one raw JSON artifact per captured command."""
        raw_dir.mkdir(parents=True, exist_ok=True)
        for index, result in enumerate(results, start=1):
            filename = f"{index:03d}-{build_slug(result.section, result.title)}.json"
            (raw_dir / filename).write_text(
                json.dumps(result.to_dict(), indent=2),
                encoding="utf-8",
            )


def _capture_result(
    spec: CaptureSpec,
    completed: subprocess.CompletedProcess[str],
    elapsed: float,
) -> CaptureResult:
    """Build a normalized result from one completed capture."""
    return CaptureResult(
        section=spec.section,
        title=spec.title,
        argv=list(spec.argv),
        exit_code=completed.returncode,
        elapsed_seconds=elapsed,
        stdout=_captured_output(completed.stdout, completed.stderr),
        notes=spec.notes,
    )


def _captured_output(stdout: str, stderr: str) -> str:
    """Combine streams and remove terminal-only right padding."""
    output = stdout or ""
    if stderr.strip():
        separator = "\n--- stderr ---\n" if output.strip() else "--- stderr ---\n"
        output = f"{output}{separator}{stderr}"
    return "\n".join(line.rstrip() for line in output.splitlines())


def _capture_environment() -> dict[str, str]:
    """Return a deterministic terminal environment for capture subprocesses."""
    environment = os.environ.copy()
    environment.update(
        {
            _DOCGEN_ENV: "1",
            "NO_COLOR": "1",
            "TERM": "dumb",
            "COLUMNS": str(CAPTURE_WIDTH),
        }
    )
    environment.pop("FORCE_COLOR", None)
    return environment


def configure_docgen_console() -> None:
    """Make Typer use the deterministic documentation console."""
    from typer import rich_utils

    setattr(rich_utils, "_get_rich_console", _docgen_console)


def _docgen_console(stderr: bool = False) -> Console:
    """Build the fixed Rich console used by documentation captures."""
    from typer import rich_utils

    return Console(
        theme=_docgen_theme(),
        highlighter=rich_utils.highlighter,
        force_terminal=False,
        color_system=None,
        width=CAPTURE_WIDTH,
        legacy_windows=False,
        stderr=stderr,
    )


def _docgen_theme() -> Theme:
    """Retain Typer's semantic styles while disabling terminal color."""
    from typer import rich_utils

    return Theme(
        {
            "option": rich_utils.STYLE_OPTION,
            "switch": rich_utils.STYLE_SWITCH,
            "negative_option": rich_utils.STYLE_NEGATIVE_OPTION,
            "negative_switch": rich_utils.STYLE_NEGATIVE_SWITCH,
            "types": rich_utils.STYLE_TYPES,
            "types_sep": rich_utils.STYLE_TYPES_SEPARATOR,
            "usage": rich_utils.STYLE_USAGE,
        }
    )


def build_command_catalog() -> dict[str, object]:
    """Return a recursive catalog of the Proxbox CLI command tree."""
    from proxbox_cli import app

    root = typer.main.get_command(app)
    commands = _walk_command(root, [])
    return {
        "generated_by": "proxbox_cli.docgen",
        "command_count": len([item for item in commands if item["kind"] == "command"]),
        "group_count": len([item for item in commands if item["kind"] == "group"]),
        "commands": commands,
    }


CatalogEntry = dict[str, str | list[str]]


def _walk_command(command: Any, path: list[str]) -> list[CatalogEntry]:
    """Return one command entry followed by its recursive descendants."""
    items = [_catalog_entry(command, path)]
    commands = _subcommands(command)
    if commands is not None:
        for name in sorted(commands):
            items.extend(_walk_command(commands[name], [*path, name]))
    return items


def _catalog_entry(command: Any, path: list[str]) -> CatalogEntry:
    """Build one catalog entry from Click or Typer's command protocol."""
    full_path = "pxb" if not path else " ".join(["pxb", *path])
    return {
        "path": list(path),
        "command": full_path,
        "kind": "group" if _subcommands(command) is not None else "command",
        "summary": _summary_for(command),
        "example": _example_for(command, path),
    }


def _subcommands(command: Any) -> dict[str, Any] | None:
    """Read subcommands across external and Typer-vendored Click versions."""
    commands = getattr(command, "commands", None)
    return commands if isinstance(commands, dict) else None


def _summary_for(command: Any) -> str:
    return (command.help or command.short_help or "No help text available.").strip()


def _example_for(command: Any, path: list[str]) -> str:
    """Build a minimal example invocation for one command."""
    tokens = ["pxb", *path]
    if _subcommands(command) is not None:
        tokens.append("--help")
        return " ".join(tokens)
    for param in command.params:
        tokens.extend(_required_parameter_tokens(param))
    return " ".join(tokens)


def _required_parameter_tokens(param: Any) -> list[str]:
    """Render required argument or option tokens through Click's public protocol."""
    if getattr(param, "hidden", False) or not getattr(param, "required", False):
        return []
    name = param.name or "value"
    if getattr(param, "param_type_name", "") == "argument":
        suffix = "..." if param.nargs == -1 else ""
        return [f"<{_placeholder_for(name)}>{suffix}"]
    if getattr(param, "param_type_name", "") != "option":
        return []
    option_name = param.opts[0] if param.opts else f"--{name.replace('_', '-')}"
    if param.is_flag:
        return [option_name]
    return [option_name, f"<{_placeholder_for(name)}>"]


def _placeholder_for(value: str) -> str:
    return value.replace("_", "-").upper()


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]
