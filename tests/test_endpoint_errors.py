"""Tests for ``netbox_proxbox.services._endpoint_errors``.

Covers issue #352 — the proxbox-api ``*-nginx`` image returns ``400`` with body
``The plain HTTP request was sent to HTTPS port`` when reached over plaintext
HTTP, and an ``SSLError`` when its self-signed mkcert cert is presented to a
client that has cert verification enabled.

The tested module only depends on ``requests``; load it directly via
``importlib.util`` to avoid bootstrapping the NetBox plugin package.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests


@pytest.fixture(scope="module")
def endpoint_errors():
    module_path = (
        Path(__file__).resolve().parents[1]
        / "netbox_proxbox"
        / "services"
        / "_endpoint_errors.py"
    )
    module_name = "test_endpoint_errors_runtime"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    try:
        yield module
    finally:
        sys.modules.pop(module_name, None)


def test_translate_recognises_plain_http_on_https_port_in_message(endpoint_errors):
    exc = requests.exceptions.HTTPError(
        "400 Client Error: Bad Request for url: http://example.host:8800/openapi.json — "
        "The plain HTTP request was sent to HTTPS port"
    )
    msg = endpoint_errors.translate_request_exception(exc)
    assert "Use HTTPS" in msg
    assert "*-nginx" in msg


def test_translate_recognises_plain_http_on_https_port_in_response_body(
    endpoint_errors,
):
    response = SimpleNamespace(status_code=400, text="plain_http_on_https_port")
    exc = requests.exceptions.HTTPError("400 Client Error: Bad Request")
    exc.response = response
    msg = endpoint_errors.translate_request_exception(exc)
    assert "Use HTTPS" in msg


def test_translate_recognises_ssl_error(endpoint_errors):
    exc = requests.exceptions.SSLError(
        "HTTPSConnectionPool(host='example'): "
        "Max retries exceeded with url (CERTIFICATE_VERIFY_FAILED: self-signed certificate)"
    )
    msg = endpoint_errors.translate_request_exception(exc)
    assert "Verify SSL" in msg
    assert "self-signed" in msg


def test_translate_falls_back_to_str_for_unknown_errors(endpoint_errors):
    exc = requests.exceptions.ConnectionError("Connection refused")
    assert endpoint_errors.translate_request_exception(exc) == "Connection refused"
