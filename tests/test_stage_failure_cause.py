"""Behavior coverage for deterministic stage-failure attribution."""

from __future__ import annotations

import sys
import types

import pytest

from tests import test_preflight_diagnosis as preflight_diagnosis


sync_stages_module = preflight_diagnosis.sync_stages_module


def _run_failed_stage(module, monkeypatch, responses):
    pending = iter(responses)
    calls: list[str] = []

    def _run_sync_stream(path, query_params=None, on_frame=None, endpoint_id=None):
        calls.append(path)
        return next(pending)

    services_mod = types.ModuleType("netbox_proxbox.services")
    services_mod.run_sync_stream = _run_sync_stream
    monkeypatch.setitem(sys.modules, "netbox_proxbox.services", services_mod)
    monkeypatch.setattr(module.time, "sleep", lambda seconds: None)

    job, records = preflight_diagnosis._make_job()
    with pytest.raises(RuntimeError) as exc_info:
        module._execute_stage_sync(
            job,
            "network-interfaces",
            "/network-interfaces/stream",
            {},
            lambda event, data: None,
        )
    return str(exc_info.value), records, calls


def test_application_failure_precedes_final_transport_error(
    sync_stages_module, monkeypatch
):
    module = sync_stages_module
    application_detail = "netboxinterfacetype.bridge is not a valid choice"
    tls_detail = (
        "TLS stream open failure: EOF occurred in violation of protocol (_ssl.c:1006)"
    )
    captured_attempts = []
    compose = module._compose_stage_failure_message

    def _capture_attempts(sync_type, attempts):
        captured_attempts.extend(attempts)
        return compose(sync_type, attempts)

    monkeypatch.setattr(module, "_compose_stage_failure_message", _capture_attempts)
    monotonic_values = iter((0.0, 1.0, 1.25, 1.3, 2.0, 2.5, 2.6, 3.0, 3.75, 3.8))
    monkeypatch.setattr(module.time, "monotonic", lambda: next(monotonic_values))
    message, records, calls = _run_failed_stage(
        module,
        monkeypatch,
        [
            # A completed stream that reports ``ok=false`` is returned by
            # ``backend_proxy`` as HTTP 503 with the ``response`` envelope —
            # the same status the transport failure on attempt 3 carries.
            ({"stream": True, "detail": application_detail, "response": {}}, 503),
            ({"stream": True, "detail": application_detail, "response": {}}, 503),
            ({"stream": True, "detail": tls_detail}, 503),
        ],
    )

    assert message.startswith(
        "Stage 'network-interfaces' failed (HTTP 503): " + application_detail
    )
    assert f"Attempt 3: HTTP 503 — {tls_detail}" in message
    assert records["error"][-1] == message
    assert len(calls) == 3
    assert [attempt.attempt_index for attempt in captured_attempts] == [1, 2, 3]
    assert [attempt.status for attempt in captured_attempts] == [503, 503, 503]
    assert [attempt.classification for attempt in captured_attempts] == [
        "application",
        "application",
        "transport",
    ]
    assert [attempt.elapsed for attempt in captured_attempts] == [0.25, 0.5, 0.75]


@pytest.mark.parametrize(
    ("status", "detail", "expected"),
    [
        (502, "backend validation failed", "transport"),
        (503, "backend validation failed", "transport"),
        (504, "backend validation failed", "transport"),
        (400, "EOF occurred in violation of protocol", "transport"),
        (500, "Connection reset by peer", "transport"),
        (503, "TLS error connecting to ProxBox backend", "transport"),
        (503, "ProxBox backend stream ended without a complete event.", "transport"),
        (500, "bridge is not a valid choice", "application"),
        (422, "bridge is not a valid choice", "application"),
    ],
)
def test_attempt_classification_uses_status_or_existing_transport_phrases(
    sync_stages_module, status, detail, expected
):
    assert (
        sync_stages_module._classify_stage_failure(status, {"detail": detail})
        == expected
    )


@pytest.mark.parametrize("status", [503, 502, 504])
def test_completed_stream_reporting_failure_is_application(sync_stages_module, status):
    """``ok=false`` completes carry ``response`` and are never transport."""
    payload = {
        "stream": True,
        "detail": "netboxinterfacetype.bridge is not a valid choice",
        "response": {"ok": False, "errors": []},
    }
    assert sync_stages_module._classify_stage_failure(status, payload) == "application"


def test_completed_stream_ignores_marker_phrases_in_validation_input(
    sync_stages_module,
):
    """A completed stream is the backend's verdict; its text cannot demote it."""
    payload = {
        "stream": True,
        "detail": '[{"msg": "invalid", "input": "bad gateway timed out"}]',
        "response": {"ok": False, "errors": []},
    }
    assert sync_stages_module._classify_stage_failure(503, payload) == "application"


@pytest.mark.parametrize(
    ("kind", "status", "detail"),
    [
        ("transport", 500, "bridge is not a valid choice"),
        ("application", 503, "Connection refused"),
        ("application", 502, "TLS error connecting to ProxBox backend"),
    ],
)
def test_producer_provenance_overrides_status_and_phrases(
    sync_stages_module, kind, status, detail
):
    """``run_sync_stream`` knows whether a backend body arrived; trust it."""
    payload = {"stream": True, "detail": detail, "failure_kind": kind}
    assert sync_stages_module._classify_stage_failure(status, payload) == kind


def test_identical_failures_keep_the_existing_single_line_message(
    sync_stages_module, monkeypatch
):
    payload = {
        "error": "backend validation failed",
        "exception": "ValidationError",
    }
    message, records, calls = _run_failed_stage(
        sync_stages_module,
        monkeypatch,
        [(payload, 500), (payload, 500), (payload, 500)],
    )

    assert message == (
        "Stage 'network-interfaces' failed (HTTP 500): "
        "backend validation failed (ValidationError)"
    )
    assert records["error"][-1] == message
    assert len(calls) == 3


def test_application_failure_after_transport_errors_becomes_primary(
    sync_stages_module, monkeypatch
):
    application_detail = "bridge is not a valid choice"
    message, _records, _calls = _run_failed_stage(
        sync_stages_module,
        monkeypatch,
        [
            ({"detail": "Connection refused"}, 503),
            ({"detail": "Read timed out."}, 504),
            ({"detail": application_detail}, 500),
        ],
    )

    assert message.startswith(
        "Stage 'network-interfaces' failed (HTTP 500): " + application_detail
    )
    assert "Attempt 1: HTTP 503 — Connection refused" in message
    assert "Attempt 2: HTTP 504 — Read timed out." in message


def test_all_transport_failures_use_last_attempt_and_list_divergence(
    sync_stages_module, monkeypatch
):
    final_detail = "TLS stream open failure"
    message, _records, _calls = _run_failed_stage(
        sync_stages_module,
        monkeypatch,
        [
            ({"detail": "Connection refused"}, 502),
            ({"detail": "Read timed out."}, 503),
            ({"detail": final_detail}, 504),
        ],
    )

    assert message.startswith(
        "Stage 'network-interfaces' failed (HTTP 504): " + final_detail
    )
    assert "Attempt 1: HTTP 502 — Connection refused" in message
    assert "Attempt 2: HTTP 503 — Read timed out." in message
    assert "Attempt 3:" not in message


def test_all_transport_failures_with_same_detail_add_no_attempt_lines(
    sync_stages_module, monkeypatch
):
    detail = "Backend stream open failure"
    message, _records, _calls = _run_failed_stage(
        sync_stages_module,
        monkeypatch,
        [
            ({"detail": detail}, 503),
            ({"detail": detail}, 503),
            ({"detail": detail}, 503),
        ],
    )

    assert message == f"Stage 'network-interfaces' failed (HTTP 503): {detail}"


def test_same_detail_with_different_statuses_still_lists_attempts(
    sync_stages_module, monkeypatch
):
    """A changed status is diagnostic even when the text did not change."""
    detail = "Backend stream open failure"
    message, _records, _calls = _run_failed_stage(
        sync_stages_module,
        monkeypatch,
        [
            ({"detail": detail}, 502),
            ({"detail": detail}, 503),
            ({"detail": detail}, 504),
        ],
    )

    assert message.startswith(f"Stage 'network-interfaces' failed (HTTP 504): {detail}")
    assert f"Attempt 1: HTTP 502 — {detail}" in message
    assert f"Attempt 2: HTTP 503 — {detail}" in message
    assert "Attempt 3:" not in message


def test_readiness_advisory_fires_for_any_attempt(sync_stages_module, monkeypatch):
    """An application cause on attempt 1 must not hide a later init_ok failure."""
    application_detail = "bridge is not a valid choice"
    readiness_detail = 'backend not ready: {"init_ok": false}'
    message, records, _calls = _run_failed_stage(
        sync_stages_module,
        monkeypatch,
        [
            (
                {
                    "stream": True,
                    "detail": application_detail,
                    "response": {},
                    "failure_kind": "application",
                },
                503,
            ),
            ({"detail": readiness_detail}, 503),
            ({"detail": readiness_detail}, 503),
        ],
    )

    assert message.startswith(
        "Stage 'network-interfaces' failed (HTTP 503): " + application_detail
    )
    advisories = [
        line for line in records["error"] if "Check proxbox-api bootstrap logs" in line
    ]
    assert advisories, "the readiness advisory must still be logged"
    assert readiness_detail in advisories[0]


def test_non_retryable_failure_message_is_unchanged(sync_stages_module, monkeypatch):
    detail = "backend rejected the requested interface type"
    message, records, calls = _run_failed_stage(
        sync_stages_module,
        monkeypatch,
        [({"detail": detail}, 422)],
    )

    assert message == f"Stage 'network-interfaces' failed (HTTP 422): {detail}"
    assert records["error"][-1] == message
    assert len(calls) == 1


def test_init_ok_failure_keeps_backend_not_ready_diagnosis(
    sync_stages_module, monkeypatch
):
    detail = "init_ok is false because NetBox is unreachable"
    message, records, calls = _run_failed_stage(
        sync_stages_module,
        monkeypatch,
        [({"detail": detail}, 404)],
    )

    assert message == f"Stage 'network-interfaces' failed (HTTP 404): {detail}"
    assert records["error"][0] == (
        "Backend not ready for stage 'network-interfaces': "
        f"{detail}. Check proxbox-api bootstrap logs and verify NetBox connectivity."
    )
    assert records["error"][-1] == message
    assert len(calls) == 1


def test_divergent_attempt_detail_is_limited_to_200_characters(
    sync_stages_module, monkeypatch
):
    long_detail = "x" * 250
    message, _records, _calls = _run_failed_stage(
        sync_stages_module,
        monkeypatch,
        [
            ({"detail": long_detail}, 502),
            ({"detail": "Read timed out."}, 503),
            ({"detail": "Connection refused"}, 504),
        ],
    )

    attempt_line = next(
        line for line in message.splitlines() if line.startswith("Attempt 1:")
    )
    rendered_detail = attempt_line.split(" — ", 1)[1]
    assert len(rendered_detail) == 200
    assert rendered_detail.endswith("...")


# --- producer-to-stage integration -------------------------------------------

from tests.test_run_sync_stream import (  # noqa: E402
    _HealthResponse,
    _StreamResponse,
    _stream_context,
)
from tests.test_run_sync_stream import (  # noqa: E402
    backend_proxy_module as backend_proxy_module,  # fixture re-exported here
)


def test_production_sequence_end_to_end(  # noqa: F811 - pytest fixture injection
    sync_stages_module, backend_proxy_module, monkeypatch
):
    """The observed incident, through the real ``run_sync_stream`` producer.

    Two completed streams reject the stage (HTTP 503, ``ok=false``), then the
    third attempt fails opening the stream with a TLS error (also a 5xx). The
    job error must name the validation cause and list the TLS attempt.
    """
    import json

    import requests as _req

    bp = backend_proxy_module
    module = sync_stages_module
    application_detail = "netboxinterfacetype.bridge is not a valid choice"
    rejected = [
        "event: complete",
        "data: "
        + json.dumps(
            {
                "ok": False,
                "message": "failed",
                "errors": [{"detail": application_detail}],
            }
        ),
        "",
    ]
    stream_calls = {"count": 0}

    def fake_get(url, **kwargs):
        if url.endswith("/health"):
            return _HealthResponse()
        stream_calls["count"] += 1
        if stream_calls["count"] >= 3:
            raise _req.exceptions.SSLError("TLS error connecting to ProxBox backend")
        return _StreamResponse(list(rejected))

    monkeypatch.setattr(bp.requests, "get", fake_get)
    monkeypatch.setattr(bp, "get_fastapi_request_context", lambda: _stream_context(bp))
    sys.modules["netbox_proxbox.services"].run_sync_stream = bp.run_sync_stream
    monkeypatch.setattr(module.time, "sleep", lambda seconds: None)

    job, records = preflight_diagnosis._make_job()
    with pytest.raises(RuntimeError) as exc_info:
        module._execute_stage_sync(
            job,
            "network-interfaces",
            "/network-interfaces/stream",
            {},
            lambda event, data: None,
        )

    message = str(exc_info.value)
    assert stream_calls["count"] == 3
    assert message.startswith(
        "Stage 'network-interfaces' failed (HTTP 503): " + application_detail
    )
    assert "Attempt 3: HTTP 5" in message
    assert "TLS error" in message
    assert records["error"][-1] == message


def test_hostname_answer_outranks_ip_fallback_transport_failure_end_to_end(  # noqa: F811
    sync_stages_module, backend_proxy_module, monkeypatch
):
    """Through the real two-candidate builder: hostname answers HTTP 503 with a
    backend-authored body, the IP fallback fails TLS, on every attempt. The job
    error must carry the backend's answer, never the fallback's TLS failure."""
    import requests as _req

    bp = backend_proxy_module
    module = sync_stages_module
    application_detail = "netboxinterfacetype.bridge is not a valid choice"

    class _Body:
        status_code = 503
        closed = False

        def close(self):
            self.closed = True

        def json(self):
            return {"detail": application_detail}

    def fake_get(url, **kwargs):
        if url.endswith("/health"):
            return _HealthResponse()
        if url.startswith(_stream_context(bp).ip_address_url + "/"):
            raise _req.exceptions.SSLError("TLS error connecting to ProxBox backend")
        return _Body()

    monkeypatch.setattr(bp.requests, "get", fake_get)
    monkeypatch.setattr(bp, "get_fastapi_request_context", lambda: _stream_context(bp))
    sys.modules["netbox_proxbox.services"].run_sync_stream = bp.run_sync_stream
    monkeypatch.setattr(module.time, "sleep", lambda seconds: None)

    job, records = preflight_diagnosis._make_job()
    with pytest.raises(RuntimeError) as exc_info:
        module._execute_stage_sync(
            job,
            "network-interfaces",
            "/network-interfaces/stream",
            {},
            lambda event, data: None,
        )

    message = str(exc_info.value)
    assert message == (
        "Stage 'network-interfaces' failed (HTTP 503): " + application_detail
    ), "identical attempts collapse to the single backend-authored line"
    assert "TLS" not in message
    assert records["error"][-1] == message
