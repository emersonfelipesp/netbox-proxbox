"""Build a bug-report payload for a failed/errored/unknown Proxbox sync Job.

Consumed by :class:`~netbox_proxbox.template_content.ProxboxJobTemplateExtension`
to render the *Bug report* button and modal on the core Job detail page
(``/core/jobs/<pk>/``). This module is intentionally pure and read-only: it only
reads data already present on the ``core.Job`` row (``data``, ``error``,
``log_entries``, timestamps) and never touches Proxmox or the proxbox-api
backend. Keeping the formatting logic here (rather than in the template) makes it
unit-testable in isolation.
"""

from __future__ import annotations

from datetime import datetime
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from typing import Any
from urllib.parse import urlencode

from core.choices import JobStatusChoices

__all__ = (
    "GITHUB_ISSUES_URL",
    "GITHUB_NEW_ISSUE_URL",
    "GITHUB_REPO_URL",
    "build_bug_report_context",
    "is_reportable_status",
)

GITHUB_REPO_URL = "https://github.com/emersonfelipesp/netbox-proxbox"
GITHUB_NEW_ISSUE_URL = f"{GITHUB_REPO_URL}/issues/new"
GITHUB_ISSUES_URL = f"{GITHUB_REPO_URL}/issues"

# GitHub silently drops (or errors on) very long prefilled-issue URLs. Keep the
# prefilled body comfortably under that limit; the full metadata + logs are
# always available through the modal's copy-to-clipboard action.
_MAX_ISSUE_BODY_CHARS = 6000


def _package_version(name: str) -> str:
    """Return an installed package version, or ``"unknown"`` when unavailable."""
    try:
        return _pkg_version(name)
    except PackageNotFoundError:
        return "unknown"
    except Exception:  # noqa: BLE001 - version lookup must never break the page
        return "unknown"


def _known_statuses() -> set[str]:
    return {
        JobStatusChoices.STATUS_PENDING,
        JobStatusChoices.STATUS_SCHEDULED,
        JobStatusChoices.STATUS_RUNNING,
        JobStatusChoices.STATUS_COMPLETED,
        JobStatusChoices.STATUS_ERRORED,
        JobStatusChoices.STATUS_FAILED,
    }


def is_reportable_status(status: Any) -> bool:
    """Return ``True`` when a job status warrants a bug report.

    Reportable states are the two error terminals (``errored``, ``failed``) plus
    any *unknown* status: a blank/``None`` value or a value NetBox does not
    recognise. Healthy in-flight or completed states are never reportable.
    """
    if status in (
        JobStatusChoices.STATUS_ERRORED,
        JobStatusChoices.STATUS_FAILED,
    ):
        return True
    return status not in _known_statuses()


def _format_value(value: Any) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _format_timestamp(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    if value in (None, ""):
        return "—"
    return str(value)


def _entry_attr(entry: Any, key: str) -> Any:
    if isinstance(entry, dict):
        return entry.get(key)
    return getattr(entry, key, None)


def _format_log_lines(log_entries: Any) -> list[str]:
    lines: list[str] = []
    for entry in log_entries or []:
        timestamp = _format_timestamp(_entry_attr(entry, "timestamp"))
        level = str(_entry_attr(entry, "level") or "info").upper()
        message = _entry_attr(entry, "message")
        message = "" if message is None else str(message)
        lines.append(f"[{timestamp}] {level} {message}".rstrip())
    return lines


def _sync_block(job: Any) -> dict[str, Any]:
    data = getattr(job, "data", None)
    if isinstance(data, dict):
        block = data.get("proxbox_sync")
        if isinstance(block, dict):
            return block
    return {}


def _sync_types(sync_block: dict[str, Any]) -> str:
    params = sync_block.get("params")
    if isinstance(params, dict):
        sync_types = params.get("sync_types")
        if isinstance(sync_types, (list, tuple)) and sync_types:
            return ", ".join(str(item) for item in sync_types)
        if sync_types:
            return str(sync_types)
    return "—"


def _runtime_seconds(sync_block: dict[str, Any]) -> str:
    value = sync_block.get("runtime_seconds")
    if value is None:
        return "—"
    try:
        return f"{float(value):.1f}"
    except (TypeError, ValueError):
        return str(value)


def _build_metadata(job: Any) -> list[tuple[str, str]]:
    sync_block = _sync_block(job)
    return [
        ("netbox-proxbox", _package_version("netbox-proxbox")),
        ("NetBox", _package_version("netbox")),
        ("Job ID", _format_value(getattr(job, "pk", None))),
        ("Job UUID", _format_value(getattr(job, "job_id", None))),
        ("Name", _format_value(getattr(job, "name", None))),
        ("Status", _format_value(getattr(job, "status", None))),
        ("Queue", _format_value(getattr(job, "queue_name", None))),
        ("Created", _format_value(getattr(job, "created", None))),
        ("Started", _format_value(getattr(job, "started", None))),
        ("Completed", _format_value(getattr(job, "completed", None))),
        ("Runtime (s)", _runtime_seconds(sync_block)),
        ("Sync types", _sync_types(sync_block)),
    ]


def _build_report_text(
    metadata: list[tuple[str, str]],
    error: str,
    log_lines: list[str],
) -> str:
    meta_block = "\n".join(f"- {label}: {value}" for label, value in metadata)
    logs_block = "\n".join(log_lines) if log_lines else "(no log entries)"
    error_block = error.strip() if error and error.strip() else "(no error message)"
    return (
        "### Proxbox sync job bug report\n\n"
        "**Environment / metadata**\n"
        f"{meta_block}\n\n"
        "**Error**\n"
        f"```\n{error_block}\n```\n\n"
        "**Job logs**\n"
        f"```\n{logs_block}\n```\n"
    )


def _build_issue_url(job: Any, report_text: str, metadata: list[tuple[str, str]], error: str) -> str:
    status = _format_value(getattr(job, "status", None))
    pk = getattr(job, "pk", None)
    title = f"[Sync bug] Proxbox sync job {pk if pk is not None else ''} ({status})"
    title = " ".join(title.split())

    if len(report_text) <= _MAX_ISSUE_BODY_CHARS:
        body = report_text
    else:
        meta_block = "\n".join(f"- {label}: {value}" for label, value in metadata)
        error_block = (
            error.strip() if error and error.strip() else "(no error message)"
        )
        body = (
            "### Proxbox sync job bug report\n\n"
            "**Environment / metadata**\n"
            f"{meta_block}\n\n"
            "**Error**\n"
            f"```\n{error_block}\n```\n\n"
            "<!-- The full metadata and job logs were copied to your clipboard "
            "by the Bug report modal. Paste them below. -->\n"
        )

    query = urlencode({"title": title, "labels": "bug", "body": body})
    return f"{GITHUB_NEW_ISSUE_URL}?{query}"


def build_bug_report_context(job: Any) -> dict[str, Any]:
    """Assemble the template context for the Bug report modal.

    Returns a dict with the plugin/NetBox versions, a ``(label, value)``
    metadata list, formatted ``log_lines``, the full copy-to-clipboard
    ``report_text``, and a prefilled ``github_issue_url`` (plus the plain
    ``github_issues_url``).
    """
    metadata = _build_metadata(job)
    error = getattr(job, "error", "") or ""
    log_lines = _format_log_lines(getattr(job, "log_entries", None))
    report_text = _build_report_text(metadata, error, log_lines)
    return {
        "job": job,
        "metadata": metadata,
        "error": error.strip(),
        "log_lines": log_lines,
        "report_text": report_text,
        "github_issue_url": _build_issue_url(job, report_text, metadata, error),
        "github_issues_url": GITHUB_ISSUES_URL,
    }
