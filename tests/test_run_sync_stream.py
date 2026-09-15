"""Tests for ``run_sync_stream`` (SSE consumption for background sync jobs)."""

from __future__ import annotations

import importlib
import json
import sys
import types
from pathlib import Path

import pytest


@pytest.fixture
def backend_proxy_module(monkeypatch):
    """Load backend proxy helpers with the minimum NetBox stubs."""
    repo_root = Path(__file__).resolve().parents[1]

    netbox_module = types.ModuleType("netbox")
    netbox_plugins = types.ModuleType("netbox.plugins")
    netbox_plugins.PluginConfig = type("PluginConfig", (), {})
    monkeypatch.setitem(sys.modules, "netbox", netbox_module)
    monkeypatch.setitem(sys.modules, "netbox.plugins", netbox_plugins)

    nbp_root = types.ModuleType("netbox_proxbox")
    nbp_root.__path__ = [str(repo_root / "netbox_proxbox")]
    monkeypatch.setitem(sys.modules, "netbox_proxbox", nbp_root)

    nbp_views = types.ModuleType("netbox_proxbox.views")
    nbp_views.__path__ = [str(repo_root / "netbox_proxbox" / "views")]
    monkeypatch.setitem(sys.modules, "netbox_proxbox.views", nbp_views)

    nbp_schemas = types.ModuleType("netbox_proxbox.schemas")
    nbp_schemas.__path__ = [str(repo_root / "netbox_proxbox" / "schemas")]
    monkeypatch.setitem(sys.modules, "netbox_proxbox.schemas", nbp_schemas)

    nbp_services = types.ModuleType("netbox_proxbox.services")
    nbp_services.__path__ = [str(repo_root / "netbox_proxbox" / "services")]
    monkeypatch.setitem(sys.modules, "netbox_proxbox.services", nbp_services)

    models_stub = types.ModuleType("netbox_proxbox.models")
    models_stub.FastAPIEndpoint = type("FastAPIEndpoint", (), {})
    monkeypatch.setitem(sys.modules, "netbox_proxbox.models", models_stub)

    sys.modules.pop("netbox_proxbox.services.backend_proxy", None)
    sys.modules.pop("netbox_proxbox.utils", None)
    sys.modules.pop("netbox_proxbox.views.error_utils", None)
    sys.modules.pop("netbox_proxbox.schemas.backend_proxy", None)
    sys.modules.pop("netbox_proxbox.schemas._base", None)

    return importlib.import_module("netbox_proxbox.services.backend_proxy")


class _StreamResponse:
    """Minimal streaming ``requests`` response for ``requests.get(..., stream=True)``."""

    def __init__(self, lines: list[str], *, status_code: int = 200):
        self.status_code = status_code
        self._lines = lines
        self.closed = False

    def close(self):
        self.closed = True

    def iter_lines(self, decode_unicode: bool = True):
        yield from self._lines


class _HealthResponse:
    """Successful backend readiness probe response."""

    status_code = 200

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def close(self):
        pass

    def json(self):
        return {"init_ok": True, "status": "ready"}


class _ErrorBodyResponse:
    """Non-stream error response with JSON body."""

    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload
        self.closed = False

    def close(self):
        self.closed = True

    def json(self):
        return self._payload


def _sse_complete_ok() -> list[str]:
    return [
        "event: step",
        f"data: {json.dumps({'step': 'devices', 'status': 'started'})}",
        "",
        "event: complete",
        f"data: {json.dumps({'ok': True, 'message': 'done', 'result': {'n': 3}})}",
        "",
    ]


def _stream_context(bp):
    return bp.BackendRequestContext(
        http_url="https://proxbox.local:8800",
        ip_address_url="https://10.0.0.5:8800",
        verify_ssl=True,
        headers={"Authorization": "Bearer backend-token"},
    )


def _mock_backend_get(response):
    def fake_get(url, **kwargs):
        if url.endswith("/health"):
            assert "stream" not in kwargs
            assert kwargs.get("verify") is True
            return _HealthResponse()
        assert kwargs.get("stream") is True
        assert kwargs.get("verify") is True
        return response

    return fake_get


def test_run_sync_stream_success(backend_proxy_module, monkeypatch):
    bp = backend_proxy_module
    urls: list[str] = []

    def fake_get(url, **kwargs):
        urls.append(url)
        return _mock_backend_get(_StreamResponse(_sse_complete_ok()))(url, **kwargs)

    monkeypatch.setattr(bp.requests, "get", fake_get)
    monkeypatch.setattr(bp, "get_fastapi_request_context", lambda: _stream_context(bp))

    frames: list[tuple[str, dict]] = []

    def on_frame(ev: str, data: dict) -> None:
        frames.append((ev, data))

    payload, status = bp.run_sync_stream(
        "dcim/devices/create/stream",
        query_params={"proxmox_endpoint_ids": "1,2"},
        on_frame=on_frame,
    )
    assert [f[0] for f in frames] == ["step", "complete"]
    assert status == 200
    assert payload["stream"] is True
    assert payload["response"]["ok"] is True
    assert payload["response"]["result"]["n"] == 3
    assert payload["path"] == "dcim/devices/create/stream"
    assert urls[0] == "https://proxbox.local:8800/health"
    assert urls[1].startswith("https://proxbox.local:8800/dcim/devices/create/stream")
    # Exactly one health check + one stream request -- no double-request regression
    assert len(urls) == 2


def test_run_sync_stream_success_with_list_result(backend_proxy_module, monkeypatch):
    bp = backend_proxy_module

    lines = [
        "event: complete",
        f"data: {json.dumps({'ok': True, 'message': 'done', 'result': [{'id': 18}, {'id': 19}]})}",
        "",
    ]

    monkeypatch.setattr(
        bp.requests,
        "get",
        _mock_backend_get(_StreamResponse(lines)),
    )
    monkeypatch.setattr(bp, "get_fastapi_request_context", lambda: _stream_context(bp))

    payload, status = bp.run_sync_stream("dcim/devices/create/stream")

    assert status == 200
    assert payload["response"]["ok"] is True
    assert isinstance(payload["response"]["result"], list)
    assert payload["response"]["result"][0]["id"] == 18


def test_run_sync_stream_complete_ok_false(backend_proxy_module, monkeypatch):
    bp = backend_proxy_module
    lines = [
        "event: error",
        f"data: {json.dumps({'detail': 'x'})}",
        "",
        "event: complete",
        f"data: {json.dumps({'ok': False, 'message': 'failed', 'errors': [{'detail': 'boom'}]})}",
        "",
    ]
    monkeypatch.setattr(
        bp.requests,
        "get",
        _mock_backend_get(_StreamResponse(lines)),
    )
    monkeypatch.setattr(bp, "get_fastapi_request_context", lambda: _stream_context(bp))
    payload, status = bp.run_sync_stream("full-update/stream")
    assert status == 503
    assert "boom" in (payload.get("detail") or "")


def test_run_sync_stream_missing_complete(backend_proxy_module, monkeypatch):
    bp = backend_proxy_module
    lines = [
        "event: step",
        f"data: {json.dumps({'x': 1})}",
        "",
    ]
    monkeypatch.setattr(
        bp.requests,
        "get",
        _mock_backend_get(_StreamResponse(lines)),
    )
    monkeypatch.setattr(bp, "get_fastapi_request_context", lambda: _stream_context(bp))
    payload, status = bp.run_sync_stream("dcim/devices/create/stream")
    assert status == 502
    assert "without a complete" in payload["detail"]


def test_run_sync_stream_invalid_complete_payload(backend_proxy_module, monkeypatch):
    bp = backend_proxy_module
    lines = [
        "event: complete",
        f"data: {json.dumps({'ok': True, 'errors': {'detail': 'bad shape'}})}",
        "",
    ]
    monkeypatch.setattr(
        bp.requests,
        "get",
        _mock_backend_get(_StreamResponse(lines)),
    )
    monkeypatch.setattr(bp, "get_fastapi_request_context", lambda: _stream_context(bp))

    payload, status = bp.run_sync_stream("dcim/devices/create/stream")

    assert status == 502
    assert "invalid complete event" in payload["detail"]


def test_run_sync_stream_http_error_json(backend_proxy_module, monkeypatch):
    bp = backend_proxy_module
    monkeypatch.setattr(
        bp.requests,
        "get",
        _mock_backend_get(_ErrorBodyResponse(502, {"detail": "bad gateway"})),
    )
    monkeypatch.setattr(bp, "get_fastapi_request_context", lambda: _stream_context(bp))
    payload, status = bp.run_sync_stream("dcim/devices/create/stream")
    # run_sync_stream now propagates the actual backend HTTP status rather than
    # always falling back to 503, so a 502 from the backend is returned as 502.
    assert status == 502
    assert payload["detail"] == "bad gateway"


def test_run_sync_stream_no_fastapi_url(backend_proxy_module, monkeypatch):
    bp = backend_proxy_module
    monkeypatch.setattr(bp, "get_fastapi_request_context", lambda: None)
    payload, status = bp.run_sync_stream("full-update/stream")
    assert status == 404
    assert "No FastAPI URL" in payload["detail"]


# --------------------------------------------------------------------------- #
# Credential redaction on the stream error path.
#
# ``sync_stages.py`` logs the payload ``run_sync_stream`` returns and folds it
# into the ``RuntimeError`` that becomes ``Job.error``; ``on_frame`` json-dumps
# every SSE frame straight into the job log.  Both are long-lived and readable
# by anyone with permission to view jobs, and the sync preflight pushes the
# ``NetBoxEndpoint`` token and every ``ProxmoxEndpoint`` password into
# proxbox-api -- so a backend that echoes the rejected request back (FastAPI 422
# does exactly that) writes live credentials into NetBox.  Redaction happens at
# the producer, here, so every downstream reader is working from redacted data.
# --------------------------------------------------------------------------- #

_SECRET = "nbt_0123456789abcdef0123456789abcdef01234567"


def _assert_absent(secret: str, value: object) -> None:
    """Fail if ``secret`` survives anywhere in ``value`` (nested included)."""
    rendered = json.dumps(value, default=str)
    assert secret not in rendered, f"secret leaked: {rendered}"


def test_failed_stream_payload_redacts_echoed_credentials(
    backend_proxy_module, monkeypatch
):
    """A backend error that echoes the pushed endpoint body must not leak it."""
    bp = backend_proxy_module
    complete = {
        "ok": False,
        "message": "Sync failed.",
        "errors": [
            {
                "detail": [
                    {
                        "loc": ["body", "token"],
                        "msg": "Input should be a valid string",
                        "input": _SECRET,
                    }
                ],
                "python_exception": f"ValidationError(input_value={{'token': '{_SECRET}'}})",
                "headers": {"Authorization": f"Bearer {_SECRET}"},
            }
        ],
    }
    lines = [
        "event: complete",
        f"data: {json.dumps(complete)}",
        "",
    ]
    monkeypatch.setattr(bp.requests, "get", _mock_backend_get(_StreamResponse(lines)))
    monkeypatch.setattr(bp, "get_fastapi_request_context", lambda: _stream_context(bp))

    payload, status = bp.run_sync_stream("dcim/devices/create/stream")

    assert status == 503
    # ``response`` carries the raw ``complete`` frame verbatim -- it is the only
    # reason producer-side redaction of the whole mapping is needed rather than
    # redaction of ``detail`` alone.
    assert "response" in payload
    _assert_absent(_SECRET, payload)


def test_failed_stream_payload_keeps_diagnostic_shape(
    backend_proxy_module, monkeypatch
):
    """Redaction must keep the error diagnosable: field names and status survive."""
    bp = backend_proxy_module
    complete = {
        "ok": False,
        "errors": [
            {
                "detail": [
                    {
                        "loc": ["body", "token"],
                        "msg": "Field required",
                        "input": _SECRET,
                    }
                ]
            }
        ],
    }
    lines = ["event: complete", f"data: {json.dumps(complete)}", ""]
    monkeypatch.setattr(bp.requests, "get", _mock_backend_get(_StreamResponse(lines)))
    monkeypatch.setattr(bp, "get_fastapi_request_context", lambda: _stream_context(bp))

    payload, _status = bp.run_sync_stream("dcim/devices/create/stream")

    rendered = json.dumps(payload, default=str)
    assert "Field required" in rendered
    assert "token" in rendered  # the *name* of the rejected field, not its value
    assert payload["path"] == "dcim/devices/create/stream"
    _assert_absent(_SECRET, payload)


def test_successful_stream_payload_is_not_redacted(backend_proxy_module, monkeypatch):
    """The success payload carries sync counters, not error text -- leave it alone."""
    bp = backend_proxy_module
    monkeypatch.setattr(
        bp.requests, "get", _mock_backend_get(_StreamResponse(_sse_complete_ok()))
    )
    monkeypatch.setattr(bp, "get_fastapi_request_context", lambda: _stream_context(bp))

    payload, status = bp.run_sync_stream("dcim/devices/create/stream")

    assert status == 200
    assert payload["response"]["result"]["n"] == 3
    assert payload["response"]["message"] == "done"


def test_on_frame_receives_redacted_frames(backend_proxy_module, monkeypatch):
    """``sync_stages.py`` json-dumps every frame into the job log -- redact first."""
    bp = backend_proxy_module
    error_frame = {
        "step": "devices",
        "status": "error",
        "detail": f"push rejected: token={_SECRET}",
        "request": {"password": "hunter2", "api_key": _SECRET},
    }
    lines = [
        "event: error",
        f"data: {json.dumps(error_frame)}",
        "",
        "event: complete",
        f"data: {json.dumps({'ok': True, 'message': 'done'})}",
        "",
    ]
    monkeypatch.setattr(bp.requests, "get", _mock_backend_get(_StreamResponse(lines)))
    monkeypatch.setattr(bp, "get_fastapi_request_context", lambda: _stream_context(bp))

    frames: list[tuple[str, dict]] = []
    bp.run_sync_stream(
        "dcim/devices/create/stream", on_frame=lambda ev, d: frames.append((ev, d))
    )

    assert [f[0] for f in frames] == ["error", "complete"]
    _assert_absent(_SECRET, frames)
    _assert_absent("hunter2", frames)
    # Still diagnosable: the step and the fact that it errored survive.
    assert frames[0][1]["step"] == "devices"
    assert frames[0][1]["status"] == "error"


def test_redaction_preserves_backend_readiness_marker(
    backend_proxy_module, monkeypatch
):
    """``sync_stages.py`` branches on ``"init_ok" in detail`` -- redaction must not eat it."""
    bp = backend_proxy_module
    detail = "Backend not ready: init_ok=false, netbox_schema=pending"
    lines = [
        "event: complete",
        f"data: {json.dumps({'ok': False, 'errors': [{'detail': detail}]})}",
        "",
    ]
    monkeypatch.setattr(bp.requests, "get", _mock_backend_get(_StreamResponse(lines)))
    monkeypatch.setattr(bp, "get_fastapi_request_context", lambda: _stream_context(bp))

    payload, status = bp.run_sync_stream("dcim/devices/create/stream")

    assert status == 503
    assert "init_ok" in payload["detail"]


def test_redaction_preserves_postgres_slot_marker(backend_proxy_module, monkeypatch):
    """``_format_stage_sync_error()`` matches this phrase to explain a DB overload."""
    bp = backend_proxy_module
    marker = (
        "remaining connection slots are reserved for roles with the superuser attribute"
    )
    lines = [
        "event: complete",
        f"data: {json.dumps({'ok': False, 'errors': [{'detail': f'FATAL: {marker}'}]})}",
        "",
    ]
    monkeypatch.setattr(bp.requests, "get", _mock_backend_get(_StreamResponse(lines)))
    monkeypatch.setattr(bp, "get_fastapi_request_context", lambda: _stream_context(bp))

    payload, _status = bp.run_sync_stream("dcim/devices/create/stream")

    assert marker in payload["detail"].lower()


def test_redacted_mapping_is_fail_closed(backend_proxy_module, monkeypatch):
    """If redaction ever stops returning a mapping, wrap the *redacted* value."""
    bp = backend_proxy_module
    monkeypatch.setattr(bp, "redact_sensitive", lambda value: "[redacted: collapsed]")

    result = bp._redacted_mapping({"token": _SECRET})

    assert result == {"detail": "[redacted: collapsed]"}
    _assert_absent(_SECRET, result)


def test_stream_transport_failure_never_logs_the_raw_exception(
    backend_proxy_module, monkeypatch, caplog
):
    """The application log must get the redacted detail, not ``str(exc)``.

    ``extract_backend_error_detail()`` sweeps the exception's rendered text
    before it reaches the user — but a ``logger.exception`` beside it would
    still write the raw message (and traceback) to the application log,
    leaking the same credential the user-facing path just redacted. Both the
    return value *and* every log record must be free of the secret.
    """
    import logging

    import requests as _req

    bp = backend_proxy_module

    def _raise(*_a, **_kw):
        raise _req.exceptions.ConnectionError(
            f"connection failed while sending token='{_SECRET}'"
        )

    monkeypatch.setattr(bp.requests, "get", _raise)

    with caplog.at_level(logging.DEBUG, logger=bp.logger.name):
        result = bp._try_sync_stream_url(
            url="http://backend:8000/dcim/devices/create/stream",
            verify=True,
            path="dcim/devices/create/stream",
            query_params=None,
            context=_stream_context(bp),
            on_frame=None,
        )

    assert isinstance(result, tuple), "a transport failure returns the error tuple"
    _assert_absent(_SECRET, result[0])
    for record in caplog.records:
        rendered = record.getMessage()
        assert _SECRET not in rendered, f"secret leaked to the log: {rendered}"
        assert record.exc_info is None, (
            "a transport failure must not be logged with its raw traceback"
        )


# --- failure provenance -----------------------------------------------------


class _NonJsonErrorResponse:
    """Gateway error page: a status code with a body that is not JSON."""

    def __init__(self, status_code: int):
        self.status_code = status_code
        self.closed = False

    def close(self):
        self.closed = True

    def json(self):
        raise ValueError("not JSON")


def _try_url(bp, response_or_exc):
    def fake_get(url, **kwargs):
        if isinstance(response_or_exc, Exception):
            raise response_or_exc
        return response_or_exc

    return fake_get


def test_backend_json_error_body_is_application_provenance(
    backend_proxy_module, monkeypatch
):
    """A JSON body means proxbox-api answered — even a 5xx it authored."""
    bp = backend_proxy_module
    monkeypatch.setattr(
        bp.requests,
        "get",
        _try_url(bp, _ErrorBodyResponse(503, {"detail": "Connection refused"})),
    )
    result = bp._try_sync_stream_url(
        url="https://backend.example:8800/dcim/devices/create/stream",
        verify=True,
        path="dcim/devices/create/stream",
        query_params=None,
        context=_stream_context(bp),
        on_frame=None,
    )
    assert isinstance(result, tuple)
    assert result[3] == 503
    assert result[4] == bp.STAGE_FAILURE_APPLICATION, (
        "a transport phrase inside a backend-authored body must not demote it"
    )


def test_non_json_gateway_error_is_transport_provenance(
    backend_proxy_module, monkeypatch
):
    """An nginx 502 page never came from proxbox-api."""
    bp = backend_proxy_module
    monkeypatch.setattr(bp.requests, "get", _try_url(bp, _NonJsonErrorResponse(502)))
    result = bp._try_sync_stream_url(
        url="https://backend.example:8800/dcim/devices/create/stream",
        verify=True,
        path="dcim/devices/create/stream",
        query_params=None,
        context=_stream_context(bp),
        on_frame=None,
    )
    assert isinstance(result, tuple)
    assert result[3] == 502
    assert result[4] == bp.STAGE_FAILURE_TRANSPORT


def test_non_json_client_error_is_application_provenance(
    backend_proxy_module, monkeypatch
):
    """A non-JSON 404 is still an answer about the request, not about reaching it."""
    bp = backend_proxy_module
    monkeypatch.setattr(bp.requests, "get", _try_url(bp, _NonJsonErrorResponse(404)))
    result = bp._try_sync_stream_url(
        url="https://backend.example:8800/dcim/devices/create/stream",
        verify=True,
        path="dcim/devices/create/stream",
        query_params=None,
        context=_stream_context(bp),
        on_frame=None,
    )
    assert isinstance(result, tuple)
    assert result[4] == bp.STAGE_FAILURE_APPLICATION


def test_connection_error_is_transport_provenance(backend_proxy_module, monkeypatch):
    bp = backend_proxy_module
    import requests as _req

    monkeypatch.setattr(
        bp.requests,
        "get",
        _try_url(bp, _req.exceptions.SSLError("certificate verify failed")),
    )
    result = bp._try_sync_stream_url(
        url="https://backend.example:8800/dcim/devices/create/stream",
        verify=True,
        path="dcim/devices/create/stream",
        query_params=None,
        context=_stream_context(bp),
        on_frame=None,
    )
    assert isinstance(result, tuple)
    assert result[4] == bp.STAGE_FAILURE_TRANSPORT


def test_run_sync_stream_stamps_failure_kind_on_completed_failure(
    backend_proxy_module, monkeypatch
):
    """The production shape: ok=false completes as HTTP 503 with application provenance."""
    bp = backend_proxy_module
    lines = [
        "event: complete",
        f"data: {json.dumps({'ok': False, 'message': 'failed', 'errors': [{'detail': 'netboxinterfacetype.bridge is not a valid choice'}]})}",
        "",
    ]
    monkeypatch.setattr(bp.requests, "get", _mock_backend_get(_StreamResponse(lines)))
    monkeypatch.setattr(bp, "get_fastapi_request_context", lambda: _stream_context(bp))

    payload, status = bp.run_sync_stream("dcim/devices/create/stream")

    assert status == 503
    assert payload["failure_kind"] == bp.STAGE_FAILURE_APPLICATION
    assert "response" in payload


def test_run_sync_stream_stamps_failure_kind_on_transport_failure(
    backend_proxy_module, monkeypatch
):
    bp = backend_proxy_module
    import requests as _req

    def fake_get(url, **kwargs):
        if url.endswith("/health"):
            return _HealthResponse()
        raise _req.exceptions.SSLError("TLS error connecting")

    monkeypatch.setattr(bp.requests, "get", fake_get)
    monkeypatch.setattr(bp, "get_fastapi_request_context", lambda: _stream_context(bp))

    payload, status = bp.run_sync_stream("dcim/devices/create/stream")

    assert status >= 500
    assert payload["failure_kind"] == bp.STAGE_FAILURE_TRANSPORT


def test_run_sync_stream_keeps_the_application_cause_across_ip_fallback(
    backend_proxy_module, monkeypatch
):
    """Hostname answers with a backend-authored 503; the IP fallback fails TLS.

    The real two-candidate builder is used. The returned cause must be the
    backend's answer, not the later transport failure on the fallback URL.
    """
    bp = backend_proxy_module
    import requests as _req

    application_detail = "netboxinterfacetype.bridge is not a valid choice"
    urls: list[str] = []

    def fake_get(url, **kwargs):
        urls.append(url)
        if url.endswith("/health"):
            return _HealthResponse()
        if url.startswith(_stream_context(bp).ip_address_url + "/"):
            raise _req.exceptions.SSLError("TLS error connecting to ProxBox backend")
        return _ErrorBodyResponse(503, {"detail": application_detail})

    monkeypatch.setattr(bp.requests, "get", fake_get)
    monkeypatch.setattr(bp, "get_fastapi_request_context", lambda: _stream_context(bp))

    payload, status = bp.run_sync_stream("dcim/devices/create/stream")

    assert len(payload["requested_urls"]) == 2, "the IP fallback must have been tried"
    assert status == 503
    assert payload["failure_kind"] == bp.STAGE_FAILURE_APPLICATION
    assert payload["detail"] == application_detail


def test_run_sync_stream_reports_last_transport_failure_when_no_candidate_answers(
    backend_proxy_module, monkeypatch
):
    bp = backend_proxy_module
    import requests as _req

    def fake_get(url, **kwargs):
        if url.endswith("/health"):
            return _HealthResponse()
        if url.startswith(_stream_context(bp).ip_address_url + "/"):
            raise _req.exceptions.SSLError("handshake failed")
        # A non-JSON 502 page is a transport failure that still allows the
        # IP fallback to be tried.
        return _NonJsonErrorResponse(502)

    monkeypatch.setattr(bp.requests, "get", fake_get)
    monkeypatch.setattr(bp, "get_fastapi_request_context", lambda: _stream_context(bp))

    payload, status = bp.run_sync_stream("dcim/devices/create/stream")

    assert len(payload["requested_urls"]) == 2
    assert payload["failure_kind"] == bp.STAGE_FAILURE_TRANSPORT
    assert "TLS" in payload["detail"], "the last transport failure is reported"


def test_invalid_complete_event_is_application_provenance(
    backend_proxy_module, monkeypatch
):
    """A frame the plugin cannot parse is the backend's answer (version skew)."""
    bp = backend_proxy_module
    lines = [
        "event: complete",
        "data: " + json.dumps({"ok": "not-a-bool-shape", "x": []}),
        "",
    ]
    monkeypatch.setattr(bp.requests, "get", _mock_backend_get(_StreamResponse(lines)))
    monkeypatch.setattr(bp, "get_fastapi_request_context", lambda: _stream_context(bp))

    payload, status = bp.run_sync_stream("dcim/devices/create/stream")

    assert status == 502
    assert "invalid complete event" in payload["detail"]
    assert payload["failure_kind"] == bp.STAGE_FAILURE_APPLICATION


def test_backend_not_ready_is_transport_provenance(backend_proxy_module, monkeypatch):
    bp = backend_proxy_module
    monkeypatch.setattr(bp, "get_fastapi_request_context", lambda: _stream_context(bp))
    monkeypatch.setattr(
        bp, "wait_for_backend_ready", lambda ctx: (False, "init_ok=false")
    )

    payload, status = bp.run_sync_stream("dcim/devices/create/stream")

    assert status == 503
    assert payload["failure_kind"] == bp.STAGE_FAILURE_TRANSPORT
    assert "init_ok" in payload["detail"]


def test_missing_backend_url_is_application_provenance(
    backend_proxy_module, monkeypatch
):
    bp = backend_proxy_module
    monkeypatch.setattr(bp, "get_fastapi_request_context", lambda: None)

    payload, status = bp.run_sync_stream("dcim/devices/create/stream")

    assert status == 404
    assert payload["failure_kind"] == bp.STAGE_FAILURE_APPLICATION


def test_list_shaped_json_error_is_application_provenance(
    backend_proxy_module, monkeypatch
):
    """A JSON list under a 5xx is a backend answer (usually version skew)."""
    bp = backend_proxy_module
    monkeypatch.setattr(
        bp.requests,
        "get",
        _try_url(bp, _ErrorBodyResponse(503, [{"detail": "schema-skew failure"}])),
    )
    result = bp._try_sync_stream_url(
        url="https://backend.example:8800/dcim/devices/create/stream",
        verify=True,
        path="dcim/devices/create/stream",
        query_params=None,
        context=_stream_context(bp),
        on_frame=None,
    )
    assert isinstance(result, tuple)
    assert result[4] == bp.STAGE_FAILURE_APPLICATION
    assert result[0] == "schema-skew failure"


def test_scalar_json_error_is_application_provenance(backend_proxy_module, monkeypatch):
    bp = backend_proxy_module
    monkeypatch.setattr(
        bp.requests, "get", _try_url(bp, _ErrorBodyResponse(500, "worker crashed"))
    )
    result = bp._try_sync_stream_url(
        url="https://backend.example:8800/dcim/devices/create/stream",
        verify=True,
        path="dcim/devices/create/stream",
        query_params=None,
        context=_stream_context(bp),
        on_frame=None,
    )
    assert isinstance(result, tuple)
    assert result[4] == bp.STAGE_FAILURE_APPLICATION
    assert result[0] == "worker crashed"


def _rebinding_backend(bp, monkeypatch, after_rebind):
    """First request 401s and rebinds; ``after_rebind`` answers the retry."""
    import requests as _req

    calls = {"n": 0}

    def fake_get(url, **kwargs):
        if url.endswith("/health"):
            return _HealthResponse()
        calls["n"] += 1
        if calls["n"] == 1:
            return _ErrorBodyResponse(401, {"detail": "Invalid API key"})
        if isinstance(after_rebind, Exception):
            raise after_rebind
        return after_rebind

    monkeypatch.setattr(bp.requests, "get", fake_get)
    monkeypatch.setattr(bp, "get_fastapi_request_context", lambda: _stream_context(bp))
    monkeypatch.setattr(
        bp,
        "_handle_auth_registration_and_retry",
        lambda context, endpoint_id=None: _stream_context(bp),
    )
    return _req


def test_rebind_starts_a_new_epoch_so_the_authenticated_answer_is_reported(
    backend_proxy_module, monkeypatch
):
    """The 401 that triggered a successful rebind is resolved; the retry's answer wins."""
    bp = backend_proxy_module
    _rebinding_backend(
        bp,
        monkeypatch,
        _ErrorBodyResponse(403, {"detail": "Authenticated key lacks sync permission"}),
    )

    payload, status = bp.run_sync_stream("dcim/devices/create/stream")

    assert status == 403
    assert payload["detail"] == "Authenticated key lacks sync permission"
    assert payload["failure_kind"] == bp.STAGE_FAILURE_APPLICATION


def test_rebind_followed_by_transport_failure_reports_the_transport_failure(
    backend_proxy_module, monkeypatch
):
    import requests as _req

    bp = backend_proxy_module
    _rebinding_backend(bp, monkeypatch, _req.exceptions.SSLError("handshake"))

    payload, status = bp.run_sync_stream("dcim/devices/create/stream")

    assert payload["failure_kind"] == bp.STAGE_FAILURE_TRANSPORT
    assert "Invalid API key" not in payload["detail"]
    assert "TLS" in payload["detail"]
