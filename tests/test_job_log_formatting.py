"""Source contract: job log messages must be pre-formatted, not %-style.

Reported across netbox-proxbox issues #614/#616/#617 — every sync job log the
users pasted contained literal placeholders instead of values::

    Info | Preflight: API key verified — %s
    Info | Preflight: synced NetBox endpoint '%s' to proxbox-api backend
    Info | Running SSE sync for Proxmox endpoint %s (backend id %s)

NetBox records job log entries through ``core.dataclasses.JobLogEntry``::

    @classmethod
    def from_logrecord(cls, record: logging.LogRecord):
        return cls(record.levelname.lower(), record.msg)

It stores ``record.msg`` — the *raw* format string. Python only merges
``record.args`` into the text inside ``record.getMessage()``, which NetBox never
calls. So ``job.logger.info("... %s", value)`` persists the literal ``%s`` and
silently drops ``value``, making sync jobs far harder to diagnose (exactly the
logs these issues were reported with).

Messages sent to a job logger must therefore be fully formatted before the call.
The module logger (``logging.getLogger(__name__)``) is unaffected — it renders
normally — so this contract is scoped to ``job.logger`` / ``self.logger`` calls.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
PLUGIN_ROOT = REPO_ROOT / "netbox_proxbox"

LOG_LEVELS = {"debug", "info", "warning", "error", "critical", "exception"}


def _job_logger_calls_with_args(path: pathlib.Path) -> list[tuple[int, str]]:
    """Return ``(line, source)`` for job-logger calls passing %-style args."""
    tree = ast.parse(path.read_text())
    offenders: list[tuple[int, str]] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr not in LOG_LEVELS:
            continue

        # Match `<something>.logger.<level>(...)` -- job.logger / self.logger /
        # self.job.logger. A bare module-level `logger.<level>()` is fine.
        owner = func.value
        if not isinstance(owner, ast.Attribute) or owner.attr != "logger":
            continue

        # A second positional argument means %-style interpolation, which the
        # NetBox job log never applies.
        if len(node.args) > 1:
            offenders.append((node.lineno, ast.unparse(node.func)))

    return offenders


PLUGIN_MODULES = sorted(
    p for p in PLUGIN_ROOT.rglob("*.py") if "migrations" not in p.parts
)


@pytest.mark.parametrize(
    "module_path", PLUGIN_MODULES, ids=lambda p: str(p.relative_to(PLUGIN_ROOT))
)
def test_job_logger_calls_are_preformatted(module_path):
    """No ``job.logger.<level>("... %s", value)`` anywhere in the plugin."""
    offenders = _job_logger_calls_with_args(module_path)

    assert not offenders, (
        f"{module_path.relative_to(REPO_ROOT)}: NetBox stores LogRecord.msg verbatim, "
        "so %-style args are dropped and the placeholder is shown to operators. "
        "Pre-format the message (f-string) instead:\n"
        + "\n".join(f"  line {line}: {call}(...)" for line, call in offenders)
    )


def test_contract_detects_the_original_regression():
    """The checker must actually flag the shape these issues were reported with."""
    sample = (
        "def run(job):\n"
        '    job.logger.info("Preflight: API key verified - %s", key_msg)\n'
        '    job.logger.info("no args here is fine")\n'
        '    logger.info("module logger renders normally - %s", value)\n'
    )
    tmp = REPO_ROOT / "tests" / "_tmp_job_log_sample.py"
    tmp.write_text(sample)
    try:
        offenders = _job_logger_calls_with_args(tmp)
    finally:
        tmp.unlink()

    assert [line for line, _ in offenders] == [2], (
        "the checker must flag the job.logger %-style call on line 2 and ignore "
        "both the no-args job.logger call and the module-level logger call"
    )
