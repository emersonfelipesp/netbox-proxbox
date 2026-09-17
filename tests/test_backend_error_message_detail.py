"""proxbox-api error bodies must surface both ``message`` and ``detail``.

Regression for the opaque ``Stage 'devices' failed (HTTP 400): Error ensuring
Proxbox tag`` job error: the backend answered ``{"message": "Error ensuring
Proxbox tag", "detail": ""}`` and the plugin's ``detail or message`` read kept
only the outer message; with a populated detail it dropped the message instead.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from tests import test_preflight_diagnosis as preflight_diagnosis
from tests.test_run_sync_stream import backend_proxy_module  # noqa: F401 - fixture

sync_stages_module = preflight_diagnosis.sync_stages_module


def _load_backend_errors():
    """Load the pure helper by path: ``netbox_proxbox/__init__`` imports NetBox."""
    path = Path(__file__).resolve().parents[1] / "netbox_proxbox" / "backend_errors.py"
    spec = importlib.util.spec_from_file_location("_backend_errors_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


combine_backend_message_and_detail = (
    _load_backend_errors().combine_backend_message_and_detail
)

TAG_MESSAGE = "Error ensuring Proxbox tag"
TIMEOUT_DETAIL = (
    "NetBox did not answer 'list /api/extras/tags/' within the configured NetBox "
    "timeout of 120s (ServerTimeoutError)."
)


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"message": TAG_MESSAGE, "detail": "", "python_exception": None}, TAG_MESSAGE),
        ({"message": TAG_MESSAGE, "detail": None}, TAG_MESSAGE),
        ({"message": TAG_MESSAGE}, TAG_MESSAGE),
        (
            {
                "message": TAG_MESSAGE,
                "detail": TIMEOUT_DETAIL,
                "python_exception": None,
            },
            f"{TAG_MESSAGE}: {TIMEOUT_DETAIL}",
        ),
        ({"detail": TIMEOUT_DETAIL}, TIMEOUT_DETAIL),
        ({"message": TAG_MESSAGE, "detail": TAG_MESSAGE}, TAG_MESSAGE),
        (
            {
                "message": "NetBox REST request failed",
                "detail": "NetBox REST request failed: 403",
            },
            "NetBox REST request failed: 403",
        ),
        (
            {
                "message": "NetBox REST request failed",
                "detail": '{"error": "FATAL", "exception": "X"}',
            },
            '{"error": "FATAL", "exception": "X"}',
        ),
        ({"message": "", "detail": ""}, None),
        ({}, None),
        ({"message": TAG_MESSAGE, "detail": {"nested": True}}, '{"nested": true}'),
        (
            {
                "detail": [
                    {"loc": ["query", "x"], "msg": "field required", "type": "missing"}
                ]
            },
            '[{"loc": ["query", "x"], "msg": "field required", "type": "missing"}]',
        ),
        (
            {"message": "Validation failed", "detail": [{"msg": "field required"}]},
            '[{"msg": "field required"}]',
        ),
        ({"message": TAG_MESSAGE, "detail": {}}, TAG_MESSAGE),
        ({"message": TAG_MESSAGE, "detail": []}, TAG_MESSAGE),
    ],
    ids=[
        "empty-detail-keeps-message",
        "null-detail",
        "message-only",
        "both-distinct-combined",
        "detail-only",
        "identical-not-duplicated",
        "detail-already-contains-message",
        "json-metadata-detail-untouched",
        "both-empty",
        "empty-payload",
        "dict-detail-serialised",
        "fastapi-validation-list-detail-preserved",
        "list-detail-not-prefixed",
        "empty-dict-detail-falls-back-to-message",
        "empty-list-detail-falls-back-to-message",
    ],
)
def test_combine_backend_message_and_detail(payload, expected):
    assert (
        combine_backend_message_and_detail(payload, render_structured=True) == expected
    )


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"message": TAG_MESSAGE, "detail": {"nested": True}}, TAG_MESSAGE),
        (
            {
                "detail": [
                    {"msg": "field required", "input": {"name": "connection refused"}}
                ]
            },
            None,
        ),
        (
            {"message": TAG_MESSAGE, "detail": TIMEOUT_DETAIL},
            f"{TAG_MESSAGE}: {TIMEOUT_DETAIL}",
        ),
    ],
    ids=[
        "dict-detail-ignored",
        "list-detail-with-input-echo-ignored",
        "strings-unchanged",
    ],
)
def test_combine_default_never_renders_structured_detail(payload, expected):
    """The stream-path default keeps FastAPI ``input`` echoes out of the cause text."""
    assert combine_backend_message_and_detail(payload) == expected


def test_combine_never_reads_python_exception():
    payload = {
        "message": TAG_MESSAGE,
        "detail": "",
        "python_exception": "Authorization: Token secret",
    }
    assert combine_backend_message_and_detail(payload) == TAG_MESSAGE


def test_combine_serialises_structured_detail_deterministically():
    detail = {"b": 1, "a": {"z": True, "y": None}}
    assert combine_backend_message_and_detail(
        {"detail": detail}, render_structured=True
    ) == ('{"a": {"y": null, "z": true}, "b": 1}')


class _JsonErrorResponse:
    def __init__(self, status_code: int, payload: object) -> None:
        self.status_code = status_code
        self._payload = payload
        self.url = "https://backend.example/dcim/devices/create/stream"

    def json(self) -> object:
        return self._payload

    def close(self) -> None:
        pass


def _http_error_detail(
    bp, status: int, payload: object
) -> tuple[str | None, int | None]:
    detail, _retry, _ctx, http_status, kind = bp._stream_http_error(
        _JsonErrorResponse(status, payload),
        url="https://backend.example/dcim/devices/create/stream",
        path="dcim/devices/create/stream",
        context=bp.BackendRequestContext(
            http_url="https://backend.example",
            ip_address_url=None,
            headers={},
            verify_ssl=True,
        ),
        endpoint_id=None,
        auth_register_attempted=True,
    )
    assert kind == bp.STAGE_FAILURE_APPLICATION
    return detail, http_status


def test_stream_http_error_reports_message_and_detail(backend_proxy_module):  # noqa: F811
    bp = backend_proxy_module
    detail, status = _http_error_detail(
        bp,
        504,
        {"message": TAG_MESSAGE, "detail": TIMEOUT_DETAIL, "python_exception": None},
    )
    assert status == 504
    assert detail == f"{TAG_MESSAGE}: {TIMEOUT_DETAIL}"


def test_stream_http_error_empty_detail_keeps_message(backend_proxy_module):  # noqa: F811
    bp = backend_proxy_module
    detail, status = _http_error_detail(
        bp, 400, {"message": TAG_MESSAGE, "detail": "", "python_exception": None}
    )
    assert status == 400
    assert detail == TAG_MESSAGE


def test_stream_http_error_keeps_fastapi_validation_list(backend_proxy_module):  # noqa: F811
    bp = backend_proxy_module
    secret = "nbt_0123456789abcdef0123456789abcdef01234567"
    body = {
        "detail": [
            {
                "loc": ["query", "proxmox_endpoint_ids"],
                "msg": "field required",
                "type": "missing",
                "input": {"token": secret},
            }
        ]
    }
    detail, status = _http_error_detail(bp, 422, body)
    assert status == 422
    assert detail is not None
    assert "field required" in detail
    assert "proxmox_endpoint_ids" in detail
    assert secret not in detail


def test_stream_http_error_keeps_dict_detail_without_message(backend_proxy_module):  # noqa: F811
    bp = backend_proxy_module
    detail, _status = _http_error_detail(
        bp, 500, {"detail": {"error": "FATAL", "exception": "X"}}
    )
    assert detail == '{"error": "FATAL", "exception": "X"}'


def test_json_error_detail_combines_backend_fields(backend_proxy_module):  # noqa: F811
    helper = backend_proxy_module._json_error_detail
    assert helper({"message": TAG_MESSAGE, "detail": ""}) == TAG_MESSAGE
    assert helper({"message": TAG_MESSAGE, "detail": TIMEOUT_DETAIL}) == (
        f"{TAG_MESSAGE}: {TIMEOUT_DETAIL}"
    )
    # Non-dict shapes are unchanged.
    assert (
        helper([{"msg": "field required", "loc": ["query", "x"]}]) == "field required"
    )
    assert helper("plain text") == "plain text"
    assert helper(None) is None


def test_extract_backend_error_text_combines_backend_fields(sync_stages_module):
    sync_types = sys.modules["netbox_proxbox.sync_types"]
    extract = sync_types._extract_backend_error_text
    assert extract({"message": TAG_MESSAGE, "detail": ""}) == TAG_MESSAGE
    assert extract({"message": TAG_MESSAGE, "detail": TIMEOUT_DETAIL}) == (
        f"{TAG_MESSAGE}: {TIMEOUT_DETAIL}"
    )
    # Structured detail stays out of the classifier's haystack (``input`` echo).
    assert (
        extract({"detail": [{"msg": "x", "input": {"name": "connection refused"}}]})
        is None
    )
    assert extract({"message": TAG_MESSAGE, "detail": {"nested": True}}) == TAG_MESSAGE
    assert extract({"error": "stream broke"}) == "stream broke"
    assert extract({"errors": [{"detail": "nested cause"}]}) == "nested cause"
    assert extract({}) is None


def test_stage_failure_message_names_both_message_and_cause(sync_stages_module):
    sync_types = sys.modules["netbox_proxbox.sync_types"]
    payload = {
        "message": TAG_MESSAGE,
        "detail": TIMEOUT_DETAIL,
        "python_exception": None,
    }
    attempt = sync_types._StageFailureAttempt(
        attempt_index=1,
        status=504,
        detail=sync_types._extract_backend_error_text(payload) or str(payload),
        classification="transport",
        elapsed=120.0,
        payload=payload,
    )
    message = sync_types._compose_stage_failure_message("devices", [attempt])
    assert message.startswith("Stage 'devices' failed (HTTP 504): ")
    assert TAG_MESSAGE in message
    assert "ServerTimeoutError" in message
