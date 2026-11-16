"""Exercise real readiness control flow with fake clock, Docker, and HTTP I/O."""

from __future__ import annotations

import json
import subprocess
import urllib.error
from types import SimpleNamespace

import pytest

from scripts import e2e_readiness as readiness


@pytest.mark.parametrize(
    "state",
    [
        {"Status": "exited", "ExitCode": 1},
        {"Status": "dead"},
        {"Status": "paused"},
        {"Status": "unknown"},
        {"Status": "running", "Health": {"Status": "unhealthy"}},
    ],
)
def test_terminal_container_stops_before_probe_or_sleep(monkeypatch, state):
    monkeypatch.setattr(readiness, "inspect_state", lambda name, timeout: state)
    monkeypatch.setattr(
        readiness.time,
        "sleep",
        lambda seconds: pytest.fail("Slept after terminal container"),
    )
    with pytest.raises(readiness.ReadinessFailure, match="Required container netbox"):
        readiness.wait_until_ready(
            ["netbox"], lambda *args: pytest.fail("Probed terminal container"), 1200
        )


def test_healthy_http_does_not_mask_another_failed_required_container(monkeypatch):
    monkeypatch.setattr(
        readiness,
        "inspect_state",
        lambda name, timeout: {"Status": "dead" if name == "redis" else "running"},
    )
    with pytest.raises(readiness.ReadinessFailure, match="redis"):
        readiness.wait_until_ready(["netbox", "redis"], lambda *args: True, 1200)


def test_slow_starting_containers_keep_their_deadline(monkeypatch):
    clock = [0.0]
    inspections = []
    monkeypatch.setattr(readiness.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        readiness.time,
        "sleep",
        lambda seconds: clock.__setitem__(0, clock[0] + seconds),
    )

    def inspect(name, timeout):
        inspections.append((name, timeout))
        return {"Status": "running", "Health": {"Status": "starting"}}

    monkeypatch.setattr(readiness, "inspect_state", inspect)
    readiness.wait_until_ready(
        ["netbox"], lambda states, remaining: clock[0] >= 1198, 1200
    )
    assert clock[0] == 1198
    assert len(inspections) == 600
    assert inspections[-1][1] == 2


def test_deadline_bounds_sleep_and_never_grants_an_extra_probe(monkeypatch):
    clock = [0.0]
    probes = []
    monkeypatch.setattr(readiness.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        readiness.time,
        "sleep",
        lambda seconds: clock.__setitem__(0, clock[0] + seconds),
    )
    monkeypatch.setattr(
        readiness, "inspect_state", lambda name, timeout: {"Status": "running"}
    )
    with pytest.raises(readiness.ReadinessFailure, match="within 3s"):
        readiness.wait_until_ready(
            ["netbox"], lambda states, timeout: probes.append(timeout) or False, 3
        )
    assert probes == [3, 1]
    assert clock[0] == 3


def test_inspection_timeout_consumes_the_shared_deadline(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(readiness.time, "monotonic", lambda: clock[0])

    def inspect(name, timeout):
        clock[0] += timeout
        return {"Status": "running"}

    monkeypatch.setattr(readiness, "inspect_state", inspect)
    with pytest.raises(readiness.ReadinessFailure, match="within 5s"):
        readiness.wait_until_ready(
            ["netbox"], lambda *args: pytest.fail("Probe after deadline"), 5
        )


def test_missing_container_fails_closed(monkeypatch):
    def inspect(name, timeout):
        raise subprocess.CalledProcessError(1, ["docker", "inspect", name])

    monkeypatch.setattr(readiness, "inspect_state", inspect)
    with pytest.raises(subprocess.CalledProcessError):
        readiness.wait_until_ready(["netbox"], lambda *args: True, 60)


def test_cli_failure_prints_full_diagnostics_and_returns_failure(monkeypatch, capsys):
    monkeypatch.setattr(
        readiness.sys,
        "argv",
        [
            "readiness",
            "--required",
            "netbox",
            "redis",
            "--timeout",
            "1200",
            "--url",
            "http://127.0.0.1/api/",
        ],
    )
    calls = []

    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        if "--format" in argv:
            return SimpleNamespace(
                stdout=json.dumps({"Status": "exited", "ExitCode": 17})
            )
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(readiness.subprocess, "run", run)
    assert readiness.main() == 1
    assert "ExitCode" in capsys.readouterr().err
    assert [argv for argv, _ in calls if "--format" not in argv] == [
        ["docker", "inspect", "netbox"],
        ["docker", "logs", "netbox"],
        ["docker", "inspect", "redis"],
        ["docker", "logs", "redis"],
    ]
    assert all("--tail" not in argv for argv, _ in calls)


@pytest.mark.parametrize(
    "status,expected", [(200, True), (401, True), (404, True), (503, False)]
)
def test_http_error_status_is_classified_without_accepting_server_failure(
    monkeypatch, status, expected
):
    def open_url(*args, **kwargs):
        raise urllib.error.HTTPError(args[0], status, "status", {}, None)

    monkeypatch.setattr(
        readiness.urllib.request,
        "build_opener",
        lambda *args: SimpleNamespace(open=open_url),
    )
    assert readiness.http_ready("http://127.0.0.1/api/", 5, False) is expected


def test_unreachable_http_is_not_ready(monkeypatch):
    def open_url(*args, **kwargs):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(
        readiness.urllib.request,
        "build_opener",
        lambda *args: SimpleNamespace(open=open_url),
    )
    assert readiness.http_ready("http://127.0.0.1/api/", 5, False) is False


def test_health_probe_requires_healthy_state():
    assert not readiness.selected_probe(
        {"db": {"Health": {"Status": "starting"}}},
        5,
        healthy="db",
        url=None,
        insecure=False,
    )
    assert readiness.selected_probe(
        {"db": {"Health": {"Status": "healthy"}}},
        5,
        healthy="db",
        url=None,
        insecure=False,
    )


def test_terminal_first_container_prevents_delayed_inspection_of_other_services(
    monkeypatch,
):
    inspected = []

    def inspect(name, timeout):
        inspected.append(name)
        assert name == "netbox"
        return {"Status": "dead"}

    monkeypatch.setattr(readiness, "inspect_state", inspect)
    with pytest.raises(readiness.ReadinessFailure):
        readiness.wait_until_ready(
            ["netbox", "slow-other-service"], lambda *args: True, 1200
        )
    assert inspected == ["netbox"]


def test_invalid_docker_state_is_refused(monkeypatch):
    monkeypatch.setattr(
        readiness.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(stdout="{}"),
    )
    with pytest.raises(readiness.ReadinessFailure, match="Invalid container state"):
        readiness.inspect_state("netbox", 5)


@pytest.mark.parametrize("timeout,interval", [(0, 2), (10, 0), (-1, 2)])
def test_invalid_deadlines_are_refused(timeout, interval):
    with pytest.raises(ValueError, match="must be positive"):
        readiness.wait_until_ready(["netbox"], lambda *args: True, timeout, interval)


def test_healthy_cli_target_completes_successfully(monkeypatch):
    monkeypatch.setattr(
        readiness.sys,
        "argv",
        ["readiness", "--required", "db", "--timeout", "60", "--healthy", "db"],
    )
    monkeypatch.setattr(
        readiness,
        "inspect_state",
        lambda *args: {"Status": "running", "Health": {"Status": "healthy"}},
    )
    assert readiness.main() == 0


def test_health_target_must_belong_to_required_containers(monkeypatch):
    monkeypatch.setattr(
        readiness.sys,
        "argv",
        ["readiness", "--required", "db", "--timeout", "60", "--healthy", "other"],
    )
    with pytest.raises(SystemExit) as result:
        readiness.main()
    assert result.value.code == 2


def test_diagnostic_failure_does_not_raise_or_hide_original_refusal(
    monkeypatch, capsys
):
    def run(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    monkeypatch.setattr(readiness.subprocess, "run", run)
    readiness.dump_diagnostics(["netbox"])
    assert "Diagnostic failed for netbox" in capsys.readouterr().err


def test_http_success_uses_bounded_probe_and_explicit_mock_tls_option(monkeypatch):
    from contextlib import nullcontext

    calls = []

    def open_url(url, **kwargs):
        calls.append((url, kwargs))
        return nullcontext(SimpleNamespace(status=200))

    monkeypatch.setattr(
        readiness.urllib.request,
        "build_opener",
        lambda *args: SimpleNamespace(open=open_url),
    )
    assert readiness.http_ready("https://127.0.0.1/health", 2, True)
    assert calls == [("https://127.0.0.1/health", {"timeout": 2})]


def test_http_probe_does_not_follow_redirects():
    handler = readiness.KeepProbeResponse()
    assert (
        handler.redirect_request(None, None, 302, "redirect", {}, "https://example.com")
        is None
    )


def test_http_selection_uses_the_shared_remaining_timeout(monkeypatch):
    observed = []
    monkeypatch.setattr(
        readiness, "http_ready", lambda *args: observed.append(args) or True
    )
    assert readiness.selected_probe(
        {}, 2, healthy=None, url="http://127.0.0.1/", insecure=False
    )
    assert observed == [("http://127.0.0.1/", 2, False)]


def test_probe_runtime_consumes_remaining_deadline_before_sleep(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(readiness.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(readiness, "inspect_state", lambda *args: {"Status": "running"})
    monkeypatch.setattr(
        readiness.time, "sleep", lambda *args: pytest.fail("Slept after deadline")
    )

    def probe(states, remaining):
        clock[0] = 5
        return False

    with pytest.raises(readiness.ReadinessFailure, match="within 5s"):
        readiness.wait_until_ready(["netbox"], probe, 5)


@pytest.mark.parametrize("completion", [5.0, 5.1])
def test_successful_probe_at_or_after_deadline_is_refused(monkeypatch, completion):
    clock = [0.0]
    monkeypatch.setattr(readiness.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(readiness, "inspect_state", lambda *args: {"Status": "running"})

    def late_probe(states, timeout):
        clock[0] = completion
        return True

    with pytest.raises(readiness.ReadinessFailure, match="within 5s"):
        readiness.wait_until_ready(["netbox"], late_probe, 5)


def test_successful_probe_before_deadline_remains_valid(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(readiness.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(readiness, "inspect_state", lambda *args: {"Status": "running"})

    def timely_probe(states, timeout):
        clock[0] = 4.9
        return True

    readiness.wait_until_ready(["netbox"], timely_probe, 5)
    assert clock[0] == 4.9
