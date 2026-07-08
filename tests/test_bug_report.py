"""Tests for the failed-sync-job bug-report helper (issue #187)."""

from __future__ import annotations

import importlib.util
import sys
import types
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

_ROOT = Path(__file__).resolve().parents[1]


def _load(monkeypatch):
    """Load netbox_proxbox.bug_report with a minimal core.choices stub.

    The module's only external dependency is ``core.choices.JobStatusChoices``,
    so a stub keeps the test independent of NetBox/Django being importable.
    """
    core_module = types.ModuleType("core")
    core_choices = types.ModuleType("core.choices")
    core_choices.JobStatusChoices = SimpleNamespace(
        STATUS_PENDING="pending",
        STATUS_SCHEDULED="scheduled",
        STATUS_RUNNING="running",
        STATUS_COMPLETED="completed",
        STATUS_ERRORED="errored",
        STATUS_FAILED="failed",
    )
    core_module.choices = core_choices
    monkeypatch.setitem(sys.modules, "core", core_module)
    monkeypatch.setitem(sys.modules, "core.choices", core_choices)

    monkeypatch.delitem(sys.modules, "netbox_proxbox.bug_report", raising=False)
    path = _ROOT / "netbox_proxbox" / "bug_report.py"
    spec = importlib.util.spec_from_file_location("netbox_proxbox.bug_report", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["netbox_proxbox.bug_report"] = module
    spec.loader.exec_module(module)
    return module


def _job(**overrides):
    base = {
        "pk": 42,
        "job_id": "11111111-2222-3333-4444-555555555555",
        "name": "Proxbox Sync",
        "status": "errored",
        "queue_name": "default",
        "created": datetime(2026, 7, 8, 12, 0, tzinfo=timezone.utc),
        "started": datetime(2026, 7, 8, 12, 0, 5, tzinfo=timezone.utc),
        "completed": datetime(2026, 7, 8, 12, 1, tzinfo=timezone.utc),
        "error": "boom: backend refused connection",
        "data": {
            "proxbox_sync": {
                "runtime_seconds": 55.4,
                "params": {"sync_types": ["virtual-machines", "storage"]},
            }
        },
        "log_entries": [
            {
                "level": "info",
                "message": "starting sync",
                "timestamp": datetime(2026, 7, 8, 12, 0, 5, tzinfo=timezone.utc),
            },
            {
                "level": "error",
                "message": "stage virtual-machines failed",
                "timestamp": datetime(2026, 7, 8, 12, 0, 59, tzinfo=timezone.utc),
            },
        ],
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_is_reportable_status_error_states(monkeypatch):
    module = _load(monkeypatch)
    assert module.is_reportable_status("errored") is True
    assert module.is_reportable_status("failed") is True


def test_is_reportable_status_unknown_states(monkeypatch):
    module = _load(monkeypatch)
    # Blank / None / anything NetBox does not recognise counts as "unknown".
    assert module.is_reportable_status("") is True
    assert module.is_reportable_status(None) is True
    assert module.is_reportable_status("canceled") is True
    assert module.is_reportable_status("mystery") is True


def test_is_reportable_status_healthy_states(monkeypatch):
    module = _load(monkeypatch)
    for status in ("pending", "scheduled", "running", "completed"):
        assert module.is_reportable_status(status) is False


def test_report_text_includes_metadata_error_and_logs(monkeypatch):
    module = _load(monkeypatch)
    ctx = module.build_bug_report_context(_job())
    text = ctx["report_text"]

    assert "Proxbox sync job bug report" in text
    assert "netbox-proxbox:" in text
    assert "NetBox:" in text
    assert "boom: backend refused connection" in text
    assert "starting sync" in text
    assert "stage virtual-machines failed" in text
    # Sync types and runtime are surfaced from the proxbox_sync data block.
    assert "virtual-machines, storage" in text
    assert "55.4" in text


def test_metadata_list_and_log_lines(monkeypatch):
    module = _load(monkeypatch)
    ctx = module.build_bug_report_context(_job())

    labels = {label for label, _ in ctx["metadata"]}
    assert {"netbox-proxbox", "NetBox", "Job ID", "Status", "Sync types"} <= labels

    assert len(ctx["log_lines"]) == 2
    assert "ERROR" in ctx["log_lines"][1]
    assert "stage virtual-machines failed" in ctx["log_lines"][1]


def test_github_issue_url_is_prefilled(monkeypatch):
    module = _load(monkeypatch)
    ctx = module.build_bug_report_context(_job())

    url = ctx["github_issue_url"]
    assert url.startswith(module.GITHUB_NEW_ISSUE_URL + "?")
    parsed = parse_qs(urlparse(url).query)
    assert parsed["labels"] == ["bug"]
    assert "Proxbox sync job 42" in parsed["title"][0]
    assert "errored" in parsed["title"][0]
    assert "Proxbox sync job bug report" in parsed["body"][0]

    assert ctx["github_issues_url"] == module.GITHUB_ISSUES_URL


def test_long_logs_truncate_issue_body_but_not_report(monkeypatch):
    module = _load(monkeypatch)
    huge_logs = [
        {"level": "info", "message": "x" * 200, "timestamp": None} for _ in range(200)
    ]
    ctx = module.build_bug_report_context(_job(log_entries=huge_logs))

    # Full report keeps everything; the prefilled URL body is capped and points
    # the reporter back to the clipboard contents.
    assert len(ctx["report_text"]) > module._MAX_ISSUE_BODY_CHARS
    body = parse_qs(urlparse(ctx["github_issue_url"]).query)["body"][0]
    assert len(body) <= module._MAX_ISSUE_BODY_CHARS + 500
    assert "copied to your clipboard" in body


def test_handles_missing_data_and_logs(monkeypatch):
    module = _load(monkeypatch)
    job = _job(data=None, log_entries=None, error="")
    ctx = module.build_bug_report_context(job)

    assert ctx["log_lines"] == []
    assert ctx["error"] == ""
    assert "(no error message)" in ctx["report_text"]
    assert "(no log entries)" in ctx["report_text"]
