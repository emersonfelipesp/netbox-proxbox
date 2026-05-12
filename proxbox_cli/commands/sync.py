"""CLI commands for triggering Proxbox sync jobs."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Annotated, Optional

import typer

from proxbox_cli._locate_manage import (
    ManagePyNotFoundError,
    locate_manage_py,
)
from proxbox_cli.config import load_config
from proxbox_cli.support import console, emit_cli_error, stderr

sync_app = typer.Typer(
    no_args_is_help=True, help="Run Proxbox sync jobs from the CLI."
)

JOB_PK_RE = re.compile(r"\(pk=(\d+)\)")
COMPLETE_RE = re.compile(r"\bcompleted\b", re.IGNORECASE)
FAIL_RE = re.compile(r"\b(errored|failed)\b", re.IGNORECASE)
TERMINATE_GRACE_SECONDS = 5.0


def _extract_job_pk(output: str) -> int | None:
    match = JOB_PK_RE.search(output)
    return int(match.group(1)) if match else None


def _style_line(line: str) -> str:
    """Apply prefix coloring for terminal lines without adding new content."""
    stripped = line.rstrip("\n")
    if FAIL_RE.search(stripped):
        return f"[red]{stripped}[/red]"
    if COMPLETE_RE.search(stripped):
        return f"[green]{stripped}[/green]"
    return stripped


def _build_argv(
    *,
    python: Path,
    manage_py: Path,
    wait: bool,
    timeout: int | None,
    poll_interval: float,
    worker_grace: float,
    user: str | None,
) -> list[str]:
    argv: list[str] = [
        str(python),
        "-u",
        str(manage_py),
        "proxbox_sync",
    ]
    if user:
        argv.extend(["--user", user])
    if wait:
        argv.append("--wait")
    if timeout is not None:
        argv.extend(["--timeout", str(timeout)])
    argv.extend(["--poll-interval", str(poll_interval)])
    argv.extend(["--worker-grace", str(worker_grace)])
    return argv


@sync_app.command("run")
def run_sync(
    wait: Annotated[
        bool,
        typer.Option(
            "--wait",
            help="Block until the job reaches a terminal state; mirror its exit code.",
        ),
    ] = False,
    timeout: Annotated[
        Optional[int],
        typer.Option(
            "--timeout",
            help=(
                "Max seconds to wait when --wait is set. "
                "Defaults to the management command's PROXBOX_SYNC_JOB_TIMEOUT (7200)."
            ),
        ),
    ] = None,
    poll_interval: Annotated[
        float,
        typer.Option(
            "--poll-interval",
            help="Seconds between job-status polls when --wait is set.",
        ),
    ] = 2.0,
    worker_grace: Annotated[
        float,
        typer.Option(
            "--worker-grace",
            help=(
                "Seconds to wait for an RQ worker on the default queue before "
                "failing fast when --wait is set."
            ),
        ),
    ] = 30.0,
    user: Annotated[
        Optional[str],
        typer.Option(
            "--user",
            help=(
                "Username to attribute the enqueued job to. "
                "Defaults to the oldest active superuser."
            ),
        ),
    ] = None,
    json_out: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Emit a single JSON document at exit instead of streaming output.",
        ),
    ] = False,
    netbox_path: Annotated[
        Optional[Path],
        typer.Option(
            "--netbox-path",
            help=(
                "Path to NetBox's manage.py (or a directory containing it). "
                "Overrides the walk-up, $NETBOX_PATH, and default-path resolution."
            ),
        ),
    ] = None,
) -> None:
    """Enqueue a full Proxmox→NetBox sync via the proxbox_sync management command."""
    cfg = load_config()

    try:
        location = locate_manage_py(
            override=netbox_path,
            config_manage_py=cfg.netbox_manage_py,
        )
    except ManagePyNotFoundError as exc:
        emit_cli_error(str(exc))

    argv = _build_argv(
        python=location.python,
        manage_py=location.manage_py,
        wait=wait,
        timeout=timeout,
        poll_interval=poll_interval,
        worker_grace=worker_grace,
        user=user,
    )

    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    # stderr=STDOUT is deliberate: merging into one stream avoids the
    # deadlock that splitting them risks (a child blocked on its stderr
    # write would hang us while we're blocked on a stdout read). The
    # management command writes errors through Django's styled
    # `CommandError` / `self.stderr.write`, which keeps the merged output
    # readable.
    proc = subprocess.Popen(  # noqa: S603 — argv is composed from validated inputs
        argv,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )

    try:
        if json_out:
            output, exit_code = _drain_for_json(proc, wait=wait, timeout=timeout)
            payload = {
                "exit_code": exit_code,
                "success": exit_code == 0,
                "job_pk": _extract_job_pk(output),
                "manage_py": str(location.manage_py),
                "command": argv,
                "output": output,
            }
            # Bypass Rich so the JSON document is unstyled and pipe-safe.
            sys.stdout.write(json.dumps(payload, indent=2))
            sys.stdout.write("\n")
            sys.stdout.flush()
        else:
            exit_code = _stream_lines(proc)
    except KeyboardInterrupt:
        _terminate(proc)
        raise

    raise typer.Exit(code=exit_code)


def _stream_lines(proc: subprocess.Popen[str]) -> int:
    """Relay the child's merged stdout/stderr line-by-line to the Rich console."""
    assert proc.stdout is not None  # noqa: S101 — Popen above always sets stdout
    try:
        for line in proc.stdout:
            console.print(_style_line(line), markup=True, highlight=False)
    except KeyboardInterrupt:
        _terminate(proc)
        raise
    return proc.wait()


def _drain_for_json(
    proc: subprocess.Popen[str],
    *,
    wait: bool,
    timeout: int | None,
) -> tuple[str, int]:
    """Wait for the subprocess and capture its merged output as a single string."""
    communicate_timeout = (timeout + 60) if (wait and timeout) else None
    try:
        stdout_data, _ = proc.communicate(timeout=communicate_timeout)
    except subprocess.TimeoutExpired:
        _terminate(proc)
        stdout_data, _ = proc.communicate()
        return stdout_data or "", proc.returncode if proc.returncode is not None else 1
    return stdout_data or "", proc.returncode


def _terminate(proc: subprocess.Popen[str]) -> None:
    """Send SIGTERM, wait briefly, then SIGKILL if the child is still alive."""
    if proc.poll() is not None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=TERMINATE_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
    except Exception as exc:  # noqa: BLE001 — best-effort cleanup, never re-raise
        stderr.print(f"[yellow]Could not terminate subprocess cleanly: {exc}[/yellow]")
