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
import json
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


# ── credential redaction ─────────────────────────────────────────────────────
#
# The sync-job preflight pushes the NetBox endpoint (carrying an API `token`)
# and every Proxmox endpoint (carrying `password` / `token_value`) into
# proxbox-api. FastAPI answers a schema mismatch with a 422 whose `input` echoes
# the submitted body verbatim, and the extracted detail is written to job logs
# and `Job.error` — long-lived rows readable by anyone who can view jobs. So the
# secret has to be stripped here, on the way out.


def test_validation_error_does_not_leak_the_echoed_token(error_utils_module):
    """A 422 echoing the pushed NetBoxEndpoint payload must not print its token."""
    resp = _response(
        422,
        '{"detail": [{"loc": ["body", "verify_ssl"], "msg": "field required",'
        ' "input": {"name": "nb", "token": "nbt_SUPERSECRET",'
        ' "token_key": "abcdef"}}]}',
    )
    exc = requests.exceptions.HTTPError(response=resp)

    detail, status = error_utils_module.extract_backend_error_detail(exc)

    assert status == 422
    assert "nbt_SUPERSECRET" not in detail
    assert "abcdef" not in detail
    # Still diagnosable: the operator learns which field the backend rejected.
    assert "field required" in detail
    assert "verify_ssl" in detail
    assert "[redacted]" in detail


def test_validation_error_does_not_leak_proxmox_credentials(error_utils_module):
    """The Proxmox push payload carries `password` and `token_value` too."""
    resp = _response(
        422,
        '{"detail": [{"msg": "bad payload", "input": {"user": "root@pam",'
        ' "password": "hunter2", "token_value": "uuid-secret",'
        ' "nested": {"api_key": "k-123"}}}]}',
    )
    exc = requests.exceptions.HTTPError(response=resp)

    detail, _status = error_utils_module.extract_backend_error_detail(exc)

    for secret in ("hunter2", "uuid-secret", "k-123"):
        assert secret not in detail
    assert "root@pam" in detail, "non-secret context must survive redaction"


def test_redaction_keeps_a_plain_string_detail_intact(error_utils_module):
    """Redaction must not mangle the ordinary case it does not apply to."""
    resp = _response(400, '{"detail": "VMID 100 already exists"}')
    exc = requests.exceptions.HTTPError(response=resp)

    detail, status = error_utils_module.extract_backend_error_detail(exc)

    assert status == 400
    assert detail == "VMID 100 already exists"


def test_redact_sensitive_matches_keys_not_values(error_utils_module):
    """Keys are matched, so the payload keeps its shape and stays readable."""
    redacted = error_utils_module.redact_sensitive(
        {
            "Authorization": "Bearer x",
            "note": "the password is wrong",
            "rows": [{"private_key": "-----BEGIN", "id": 4}],
        }
    )

    assert redacted["Authorization"] == "[redacted]"
    assert redacted["rows"][0]["private_key"] == "[redacted]"
    assert redacted["rows"][0]["id"] == 4
    # A *value* that merely mentions a secret is not a secret; blanking it would
    # destroy the error message without protecting anything.
    assert redacted["note"] == "the password is wrong"


def test_redact_sensitive_survives_a_self_referential_payload(error_utils_module):
    """A cyclic structure must hit the depth limit, not recurse forever."""
    payload: dict[str, object] = {"detail": "x"}
    payload["self"] = payload

    redacted = error_utils_module.redact_sensitive(payload)

    assert redacted["detail"] == "x"


def test_scalar_input_is_redacted_when_loc_names_a_credential_field(
    error_utils_module,
):
    """Key matching cannot see a secret whose own key is the neutral `input`.

    FastAPI echoes the rejected *value* under `input` and names the field it
    belongs to in the sibling `loc`.  When that field is a credential, the secret
    arrives as a bare scalar with nothing sensitive about its key — so the `loc`
    is what has to be read.
    """
    resp = _response(
        422,
        '{"detail": [{"loc": ["body", "token"], "msg": "string too short",'
        ' "input": "nbt_SUPERSECRET"}]}',
    )
    exc = requests.exceptions.HTTPError(response=resp)

    detail, status = error_utils_module.extract_backend_error_detail(exc)

    assert status == 422
    assert "nbt_SUPERSECRET" not in detail
    assert "[redacted]" in detail
    # The rejection itself still reaches the operator.
    assert "string too short" in detail
    assert "token" in detail


def test_header_style_keys_are_redacted(error_utils_module):
    """`api_key`, `X-Proxbox-API-Key`, and `ApiKey` are one field in three spellings.

    The markers are separator-free, so only the folded form matches them all;
    matching the raw key let the HTTP-header spelling through unredacted.
    """
    redacted = error_utils_module.redact_sensitive(
        {
            "X-Proxbox-API-Key": "k-123",
            "Private-Key": "-----BEGIN",
            "SSH Keys": "ssh-ed25519 AAAA",
            "keyring-id": 7,
        }
    )

    assert redacted["X-Proxbox-API-Key"] == "[redacted]"
    assert redacted["Private-Key"] == "[redacted]"
    assert redacted["SSH Keys"] == "[redacted]"
    # Folding must not turn an unrelated key into a match.
    assert redacted["keyring-id"] == 7


def test_payload_nested_past_the_depth_limit_is_redacted_not_returned_raw(
    error_utils_module,
):
    """Past the depth limit the value is dropped, not passed through.

    Returning the original object there was the hole: a body nested deeper than
    the limit skipped redaction entirely and reached the job log verbatim.
    """
    payload: object = {"token": "SUPERSECRET"}
    for _ in range(error_utils_module._REDACTION_DEPTH_LIMIT + 1):
        payload = {"wrap": payload}

    redacted = error_utils_module.redact_sensitive(payload)

    assert "SUPERSECRET" not in json.dumps(redacted)
    assert error_utils_module._REDACTED_DEEP in json.dumps(redacted)


def test_credentials_rendered_into_prose_are_swept(error_utils_module):
    """Structural redaction cannot reach a secret already rendered to a string.

    Pydantic prints the rejected object into `msg`/`python_exception` text, and
    proxbox-api quotes request headers — by then there is no mapping left to key
    match against.
    """
    resp = _response(
        400,
        json.dumps(
            {
                "detail": "rejected input_value={'token': 'nbt_SUPERSECRET'}",
                "python_exception": (
                    "AuthError: header Authorization: Bearer "
                    "eyJhbGciOiJIUzI1NiJ9.payload.sig"
                ),
            }
        ),
    )
    exc = requests.exceptions.HTTPError(response=resp)

    detail, status = error_utils_module.extract_backend_error_detail(exc)

    assert status == 400
    assert "nbt_SUPERSECRET" not in detail
    assert "eyJhbGciOiJIUzI1NiJ9.payload.sig" not in detail
    # Shape survives, so the operator still sees what failed and why.
    assert "input_value" in detail
    assert "AuthError" in detail
    assert "Authorization: [redacted]" in detail


def test_bare_bearer_token_without_a_credential_key_is_swept(error_utils_module):
    """A scheme quoted with no credential-named key in front of it still leaks."""
    swept = error_utils_module.redact_sensitive_text(
        "upstream replied 401 to header [Bearer eyJhbGciOiJIUzI1NiJ9.payload.sig]"
    )

    assert "eyJhbGciOiJIUzI1NiJ9.payload.sig" not in swept
    assert "Bearer [redacted]" in swept
    assert "upstream replied 401" in swept


def test_transport_error_text_is_swept_before_it_is_returned(error_utils_module):
    """The no-response branch has no body to key match — only the rendered text.

    That text can still quote the request that failed, credentials included.
    """
    exc = requests.exceptions.RequestException(
        "Rejected by upstream while sending token='nbt_SUPERSECRET' to /netbox/"
    )

    detail, status = error_utils_module.extract_backend_error_detail(exc)

    assert status is None
    assert "nbt_SUPERSECRET" not in detail
    assert "[redacted]" in detail
    assert "/netbox/" in detail


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


def test_proxmox_error_sweeps_the_rendered_upstream_exception(error_utils_module):
    """The ``Upstream error:`` tail must be swept, not rendered raw.

    A transport exception can echo request content — here a credential-bearing
    assignment — and this string flows into job logs and flash messages, so it
    gets the same text sweep as every other exception-rendered detail.
    """
    secret = "0123456789abcdef0123456789abcdef01234567"
    exc = requests.exceptions.ConnectionError(
        f"connection failed while sending token_value='{secret}'"
    )
    detail, status = error_utils_module.extract_proxmox_backend_error_detail(
        exc,
        proxmox_host="pve.local",
        proxmox_port=8006,
        backend_url="http://backend/proxmox/sync",
    )
    assert status is None
    assert secret not in detail
    assert "pve.local:8006" in detail, "the diagnostic target must survive the sweep"


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
