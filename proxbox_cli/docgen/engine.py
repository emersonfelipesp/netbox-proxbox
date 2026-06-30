"""Capture selected help output and build a command catalog for MkDocs."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import time
from typing import TextIO

import click
import typer

from proxbox_cli.docgen.models import (
    DEFAULT_CAPTURE_TIMEOUT_SECONDS,
    CaptureResult,
    CaptureSpec,
    build_slug,
)


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
        completed = subprocess.run(
            [sys.executable, "-m", "proxbox_cli", *spec.argv],
            capture_output=True,
            cwd=str(_repo_root()),
            text=True,
            timeout=self._timeout_seconds,
        )
        elapsed = time.perf_counter() - started
        output = completed.stdout or ""
        stderr = completed.stderr or ""
        if stderr.strip():
            output = (
                f"{output}\n--- stderr ---\n{stderr}"
                if output.strip()
                else f"--- stderr ---\n{stderr}"
            )
        return CaptureResult(
            section=spec.section,
            title=spec.title,
            argv=list(spec.argv),
            exit_code=completed.returncode,
            elapsed_seconds=elapsed,
            stdout=output.rstrip(),
            notes=spec.notes,
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


def _walk_command(command: click.Command, path: list[str]) -> list[CatalogEntry]:
    full_path = "pxb" if not path else " ".join(["pxb", *path])
    entry = {
        "path": list(path),
        "command": full_path,
        "kind": "group" if isinstance(command, click.Group) else "command",
        "summary": _summary_for(command),
        "example": _example_for(command, path),
    }

    items = [entry]
    if isinstance(command, click.Group):
        for name in sorted(command.commands):
            items.extend(_walk_command(command.commands[name], [*path, name]))
    return items


def _summary_for(command: click.Command) -> str:
    return (command.help or command.short_help or "No help text available.").strip()


def _example_for(command: click.Command, path: list[str]) -> str:
    tokens = ["pxb", *path]
    if isinstance(command, click.Group):
        tokens.append("--help")
        return " ".join(tokens)

    for param in command.params:
        if getattr(param, "hidden", False):
            continue
        if isinstance(param, click.Argument):
            label = _placeholder_for(param.name or "value")
            if param.nargs == -1:
                tokens.append(f"<{label}>...")
            else:
                tokens.append(f"<{label}>")
            continue
        if isinstance(param, click.Option) and param.required:
            option_name = (
                param.opts[0]
                if param.opts
                else f"--{(param.name or 'value').replace('_', '-')}"
            )
            if param.is_flag:
                tokens.append(option_name)
            else:
                tokens.extend(
                    [option_name, f"<{_placeholder_for(param.name or 'value')}>"]
                )

    return " ".join(tokens)


def _placeholder_for(value: str) -> str:
    return value.replace("_", "-").upper()


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]
