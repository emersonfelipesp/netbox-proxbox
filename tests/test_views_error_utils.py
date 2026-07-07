"""Behavior tests for ``netbox_proxbox.views.error_utils``.

The plugin proxies a number of operational requests to proxbox-api and then
renders the resulting error to the user. Two helpers normalize that error
output:

* ``parse_requests_response_json`` — guards against non-JSON 5xx HTML pages.
* ``extract_backend_error_detail`` / ``extract_proxmox_backend_error_detail``
  — turn ``requests`` exceptions into a user-facing message and HTTP status,
  recognising connection-refused / timeout / HTML-instead-of-JSON cases.

These helpers are pure and testable with hand-built ``requests.Response``
instances; no Django stack is required. Loading the module via importlib lets
the test run without booting NetBox.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import requests
import requests.exceptions

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def error_utils_module():
    spec = importlib.util.spec_from_file_location(
        "_netbox_proxbox_error_utils_under_test",
        REPO_ROOT / "netbox_proxbox" / "views" / "error_utils.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _response(
    status_code: int,
    body: str | bytes,
    *,
    content_type: str = "application/json",
    url: str = "http://backend/",
) -> requests.Response:
    resp = requests.Response()
    resp.status_code = status_code
    resp._content = body.encode("utf-8") if isinstance(body, str) else body
    resp.url = url
    resp.headers["Content-Type"] = content_type
    return resp


# ── parse_requests_response_json ─────────────────────────────────────────────


def test_parse_json_returns_payload_on_valid_body(error_utils_module):
    resp = _response(200, '{"ok": true, "n": 3}')
    payload, detail = error_utils_module.parse_requests_response_json(resp)
    assert payload == {"ok": True, "n": 3}
    assert detail is None


def test_parse_json_returns_user_facing_detail_for_html(error_utils_module):
    resp = _response(200, "<html>nginx</html>", content_type="text/html")
    payload, detail = error_utils_module.parse_requests_response_json(resp)
    assert payload is None
    assert detail is not None
    assert "not valid JSON" in detail
    assert "<html>nginx</html>" not in detail
    assert "Body starts with" not in detail


# ── extract_backend_error_detail (no .response set) ──────────────────────────


def test_connection_error_with_host_port_returns_targeted_message(error_utils_module):
    exc = requests.exceptions.ConnectionError(
        "HTTPSConnectionPool(host='10.0.0.5', port=8800): "
        "Max retries exceeded: connection refused"
    )
    detail, status = error_utils_module.extract_backend_error_detail(exc)
    assert status is None
    assert "10.0.0.5:8800" in detail
    assert "Connection was refused" in detail


def test_timeout_returns_timeout_message(error_utils_module):
    exc = requests.exceptions.Timeout(
        "HTTPConnectionPool(host='backend', port=8000): timed out"
    )
    detail, status = error_utils_module.extract_backend_error_detail(exc)
    assert status is None
    assert "Timed out" in detail
    assert "backend:8000" in detail


def test_other_request_exception_returns_str_form(error_utils_module):
    exc = requests.exceptions.RequestException("something wrong")
    detail, status = error_utils_module.extract_backend_error_detail(exc)
    assert status is None
    assert "something wrong" in detail


# ── extract_backend_error_detail (with .response) ────────────────────────────


def test_response_with_json_detail_field(error_utils_module):
    resp = _response(404, '{"detail": "VM not found"}')
    exc = requests.exceptions.HTTPError(response=resp)
    detail, status = error_utils_module.extract_backend_error_detail(exc)
    assert status == 404
    assert detail == "VM not found"


def test_response_with_generic_detail_prefers_message(error_utils_module):
    resp = _response(
        500,
        '{"detail": "Internal Server Error", "message": "VM disk read failed"}',
    )
    exc = requests.exceptions.HTTPError(response=resp)
    detail, status = error_utils_module.extract_backend_error_detail(exc)
    assert status == 500
    assert detail == "VM disk read failed"


def test_response_html_for_400_class_status_returns_helpful_message(error_utils_module):
    resp = _response(401, "<html>Login required</html>", content_type="text/html")
    exc = requests.exceptions.HTTPError(response=resp)
    detail, status = error_utils_module.extract_backend_error_detail(exc)
    assert status == 401
    assert "HTML instead of ProxBox API JSON" in detail
    assert "401" in detail
    assert "NetBox UI" in detail


def test_response_with_python_exception_field_appended(error_utils_module):
    resp = _response(500, '{"detail": "boom", "python_exception": "RuntimeError: x"}')
    exc = requests.exceptions.HTTPError(response=resp)
    detail, _ = error_utils_module.extract_backend_error_detail(exc)
    assert "boom" in detail
    assert "RuntimeError: x" in detail


# ── extract_proxmox_backend_error_detail (host fallback) ─────────────────────


def test_proxmox_error_falls_back_to_target_message_when_no_response(
    error_utils_module,
):
    exc = requests.exceptions.ConnectionError("connection refused")
    detail, status = error_utils_module.extract_proxmox_backend_error_detail(
        exc,
        proxmox_host="pve.local",
        proxmox_port=8006,
        backend_url="http://backend/proxmox/sync",
    )
    assert status is None
    assert "pve.local:8006" in detail
    assert "http://backend/proxmox/sync" in detail


def test_proxmox_error_delegates_when_response_is_present(error_utils_module):
    resp = _response(503, '{"detail": "Service Unavailable"}')
    exc = requests.exceptions.HTTPError(response=resp)
    detail, status = error_utils_module.extract_proxmox_backend_error_detail(
        exc,
        proxmox_host="pve.local",
        proxmox_port=8006,
        backend_url="http://backend/proxmox/sync",
    )
    assert status == 503
    assert detail == "Service Unavailable"
