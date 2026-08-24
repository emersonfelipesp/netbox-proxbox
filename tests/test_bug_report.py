"""Tests for the failed-sync-job bug-report helper (issue #187)."""

from __future__ import annotations

import sys
import types
from datetime import datetime, timezone
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

from tests.pure_loader import install_pure_package, load_anonymize, load_pure_module


def _load(monkeypatch):
    """Load netbox_proxbox.bug_report with a minimal core.choices stub.

    Its external dependencies are ``core.choices.JobStatusChoices`` and the
    sibling ``netbox_proxbox.anonymize`` (which in turn imports
    ``netbox_proxbox.redaction``), so a stub for the former plus the shared
    pure loader for the latter keeps the test independent of NetBox/Django.

    The stub packages matter: without a parent already in ``sys.modules`` those
    sibling imports would execute the real package ``__init__``, which needs
    Django.
    """
    install_pure_package(monkeypatch)
    load_anonymize(monkeypatch)

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

    return load_pure_module(monkeypatch, "netbox_proxbox.bug_report", "bug_report.py")


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


# ---------------------------------------------------------------------------
# Anonymization
#
# The payload built here is meant to be pasted into a public issue tracker, so
# these guard the boundary rather than the formatting.
# ---------------------------------------------------------------------------


def _leaky_job():
    """A job whose error and logs carry exactly what must never be published."""
    return _job(
        error="connect to node01.example.com (192.0.2.15) failed: password=hunter2",
        log_entries=[
            {
                "level": "error",
                "message": "node01.example.com unreachable at 192.0.2.15",
                "timestamp": datetime(2026, 7, 8, 12, 0, 59, tzinfo=timezone.utc),
            },
            {
                "level": "error",
                "message": "auth failed for root@pam with PVEAPIToken=abc!id=s3cr3t",
                "timestamp": datetime(2026, 7, 8, 12, 1, 0, tzinfo=timezone.utc),
            },
        ],
    )


_LEAKED_VALUES = ("node01.example.com", "192.0.2.15", "hunter2", "s3cr3t")


def test_report_text_is_anonymized(monkeypatch):
    module = _load(monkeypatch)
    ctx = module.build_bug_report_context(_leaky_job())
    for secret in _LEAKED_VALUES:
        assert secret not in ctx["report_text"]


def test_error_and_log_lines_are_anonymized(monkeypatch):
    module = _load(monkeypatch)
    ctx = module.build_bug_report_context(_leaky_job())
    blob = ctx["error"] + "\n".join(ctx["log_lines"])
    for secret in _LEAKED_VALUES:
        assert secret not in blob


def test_prefilled_issue_url_is_anonymized(monkeypatch):
    """The link is the actual egress path -- scrubbing the textarea is not enough.

    ``_build_issue_url`` embeds the body in a GitHub URL, so a regression that
    scrubbed only what the modal renders would still publish the raw text the
    moment the reporter clicks through.
    """
    module = _load(monkeypatch)
    ctx = module.build_bug_report_context(_leaky_job())
    url = ctx["github_issue_url"]
    for secret in _LEAKED_VALUES:
        assert secret not in url
    body = parse_qs(urlparse(url).query)["body"][0]
    for secret in _LEAKED_VALUES:
        assert secret not in body


def test_truncated_issue_body_is_also_anonymized(monkeypatch):
    """The over-length branch of _build_issue_url is a separate code path."""
    module = _load(monkeypatch)
    huge_logs = [
        {
            "level": "error",
            "message": "node01.example.com at 192.0.2.15 said " + "x" * 200,
            "timestamp": None,
        }
        for _ in range(200)
    ]
    ctx = module.build_bug_report_context(_leaky_job_with_logs(huge_logs))
    body = parse_qs(urlparse(ctx["github_issue_url"]).query)["body"][0]
    assert len(ctx["report_text"]) > module._MAX_ISSUE_BODY_CHARS
    for secret in ("node01.example.com", "192.0.2.15", "hunter2"):
        assert secret not in body


def _leaky_job_with_logs(log_entries):
    return _job(
        error="connect to node01.example.com (192.0.2.15) failed: password=hunter2",
        log_entries=log_entries,
    )


def test_placeholders_are_consistent_across_fields(monkeypatch):
    """A host named in the error and in a log line must get the same token."""
    module = _load(monkeypatch)
    ctx = module.build_bug_report_context(_leaky_job())
    token = "<host-1>"
    assert token in ctx["error"]
    assert any(token in line for line in ctx["log_lines"])


def test_version_metadata_is_not_scrubbed(monkeypatch):
    """A four-segment version looks like an IPv4 address; it must survive."""
    module = _load(monkeypatch)
    monkeypatch.setattr(module, "_package_version", lambda name: "1.2.3.4")
    ctx = module.build_bug_report_context(_job())
    versions = {label: value for label, value in ctx["metadata"]}
    assert versions["netbox-proxbox"] == "1.2.3.4"
    assert versions["NetBox"] == "1.2.3.4"


def test_context_is_flagged_anonymized(monkeypatch):
    """The template branches on this to tell the reporter what it is handing over."""
    module = _load(monkeypatch)
    assert module.build_bug_report_context(_job())["anonymized"] is True


def test_hostile_credential_shapes_never_reach_the_public_issue_url(monkeypatch):
    """End-to-end: every shape adversarial review found must die before egress.

    These are asserted against the **decoded** ``body`` query parameter rather
    than the modal context, because the prefilled URL is the path that actually
    publishes. Each entry leaked through the first implementation.
    """
    module = _load(monkeypatch)
    job = _job(
        error='backend rejected {"password":"hunter2"} for token_value=abc123secret',
        log_entries=[
            {
                "level": "error",
                "message": "Authorization: Bearer eyJTOKENXX rejected",
                "timestamp": datetime(2026, 7, 8, 12, 0, 59, tzinfo=timezone.utc),
            },
            {
                "level": "error",
                "message": "X-Proxbox-API-Key: k3yv4lue and token_secret=def456secret",
                "timestamp": datetime(2026, 7, 8, 12, 1, 0, tzinfo=timezone.utc),
            },
            {
                "level": "error",
                "message": "upstream said Bearer eyJhbGciOiJIUzI1NiJ9.payload",
                "timestamp": datetime(2026, 7, 8, 12, 1, 1, tzinfo=timezone.utc),
            },
        ],
    )
    ctx = module.build_bug_report_context(job)
    body = parse_qs(urlparse(ctx["github_issue_url"]).query)["body"][0]

    for secret in (
        "hunter2",
        "abc123secret",
        "def456secret",
        "k3yv4lue",
        "eyJTOKENXX",
        "eyJhbGciOiJIUzI1NiJ9",
    ):
        assert secret not in body, f"{secret} reached the prefilled issue URL"
        assert secret not in ctx["report_text"]


def test_authentication_schemes_never_reach_the_public_issue_url(monkeypatch):
    """Round-2 counterexamples, asserted against the decoded ``?body=``."""
    module = _load(monkeypatch)
    job = _job(
        error="auth=s3cr3tauthvalue session=s3cr3tsessionid encryption_key=s3cr3tfernetkey",
        log_entries=[
            {
                "level": "error",
                "message": "Authorization: Token nbt_s3cr3ttokenvalue rejected",
                "timestamp": datetime(2026, 7, 8, 12, 0, 59, tzinfo=timezone.utc),
            },
            {
                "level": "error",
                "message": (
                    "private_key: -----BEGIN RSA PRIVATE KEY-----\n"
                    "MIIEows3cr3tpemmaterial\n-----END RSA PRIVATE KEY-----"
                ),
                "timestamp": datetime(2026, 7, 8, 12, 1, 0, tzinfo=timezone.utc),
            },
            {
                "level": "error",
                "message": "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5s3cr3ted25519data admin@corp",
                "timestamp": datetime(2026, 7, 8, 12, 1, 1, tzinfo=timezone.utc),
            },
        ],
    )
    ctx = module.build_bug_report_context(job)
    body = parse_qs(urlparse(ctx["github_issue_url"]).query)["body"][0]

    for secret in (
        "s3cr3tauthvalue",
        "s3cr3tsessionid",
        "s3cr3tfernetkey",
        "nbt_s3cr3ttokenvalue",
        "s3cr3tpemmaterial",
        "s3cr3ted25519data",
    ):
        assert secret not in body, f"{secret} reached the prefilled issue URL"
        assert secret not in ctx["report_text"]


def test_an_oversized_error_alone_still_fits_the_issue_body(monkeypatch):
    """The truncated branch must budget the error, not just drop the logs.

    The earlier version removed the logs and then re-inserted the error whole,
    so a verbose backend traceback blew the limit on its own -- a 20,000
    character ``job.error`` produced a ~20,500 character body against a 6,000
    limit. GitHub rejects or silently drops a prefill that size, which loses the
    reporter the link entirely.
    """
    module = _load(monkeypatch)
    job = _job(error="boom " * 4000, log_entries=[])
    ctx = module.build_bug_report_context(job)

    body = parse_qs(urlparse(ctx["github_issue_url"]).query)["body"][0]
    assert len(body) <= module._MAX_ISSUE_BODY_CHARS
    assert "truncated" in body
    # The full text is still available through the clipboard copy.
    assert len(ctx["report_text"]) > module._MAX_ISSUE_BODY_CHARS


def test_oversized_metadata_is_also_budgeted(monkeypatch):
    """Metadata is attacker-influenced too -- a job name can be arbitrarily long."""
    module = _load(monkeypatch)
    job = _job(name="n" * 20000, error="boom " * 4000, log_entries=[])
    ctx = module.build_bug_report_context(job)
    body = parse_qs(urlparse(ctx["github_issue_url"]).query)["body"][0]
    assert len(body) <= module._MAX_ISSUE_BODY_CHARS
