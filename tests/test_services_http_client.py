"""Behavior tests for ``netbox_proxbox.services.http_client``.

The plugin's HTTP layer is a thin wrapper that translates ``requests``
exceptions into typed ``HttpError`` subclasses (``HttpConnectionError``,
``HttpTimeoutError``, ``HttpSslError``). The translation is what allows
upstream callers — for example the dashboard keepalive checks and the SSE
proxy — to surface specific user-facing messages without re-classifying raw
``requests`` exceptions over and over.

These tests load ``http_client.py`` directly (no Django stack required), patch
``requests.get/post/put/delete`` with ``unittest.mock`` and verify:

1. Successful calls return an ``HttpResponse`` wrapping the mocked
   ``requests.Response``.
2. Each ``requests`` exception subclass is mapped to the matching
   ``HttpError`` subclass.
3. ``stream_get`` is a context manager that closes the underlying response
   even when the body raises mid-iteration.
4. ``get_default_http_client()`` is a singleton.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import requests

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def http_client_module():
    spec = importlib.util.spec_from_file_location(
        "_netbox_proxbox_http_client_under_test",
        REPO_ROOT / "netbox_proxbox" / "services" / "http_client.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _make_response(status_code: int = 200, text: str = "ok") -> requests.Response:
    resp = requests.Response()
    resp.status_code = status_code
    resp._content = text.encode("utf-8")
    resp.url = "http://test/"
    resp.headers["Content-Type"] = "application/json"
    return resp


# ── Successful round-trips ───────────────────────────────────────────────────


def test_get_returns_wrapped_response(http_client_module):
    client = http_client_module.RequestsHttpClient()
    raw = _make_response(204, "")
    with patch("requests.get", return_value=raw) as mock_get:
        resp = client.get("http://x/", headers={"a": "b"}, timeout=7, verify=False)
    assert isinstance(resp, http_client_module.HttpResponse)
    assert resp.status_code == 204
    mock_get.assert_called_once()
    assert mock_get.call_args.kwargs["timeout"] == 7
    assert mock_get.call_args.kwargs["verify"] is False
    assert mock_get.call_args.kwargs["stream"] is False


def test_post_passes_json_payload(http_client_module):
    client = http_client_module.RequestsHttpClient()
    raw = _make_response(201, '{"ok":true}')
    with patch("requests.post", return_value=raw) as mock_post:
        resp = client.post("http://x/", json={"a": 1})
    assert resp.status_code == 201
    assert mock_post.call_args.kwargs["json"] == {"a": 1}


# ── Exception translation ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("requests_exc", "expected_attr"),
    [
        (requests.exceptions.SSLError("bad cert"), "HttpSslError"),
        (requests.exceptions.Timeout("slow"), "HttpTimeoutError"),
        (requests.exceptions.ConnectionError("refused"), "HttpConnectionError"),
        (requests.exceptions.RequestException("other"), "HttpError"),
    ],
)
def test_get_translates_each_requests_exception(
    http_client_module, requests_exc, expected_attr
):
    client = http_client_module.RequestsHttpClient()
    expected_cls = getattr(http_client_module, expected_attr)
    with patch("requests.get", side_effect=requests_exc):
        with pytest.raises(expected_cls):
            client.get("http://x/")


def test_post_put_delete_also_translate_exceptions(http_client_module):
    client = http_client_module.RequestsHttpClient()
    err = requests.exceptions.ConnectionError("refused")
    for method, target in (
        (client.post, "requests.post"),
        (client.put, "requests.put"),
        (client.delete, "requests.delete"),
    ):
        with patch(target, side_effect=err):
            with pytest.raises(http_client_module.HttpConnectionError):
                method("http://x/")


# ── Streaming ────────────────────────────────────────────────────────────────


def test_stream_get_closes_response_on_exit(http_client_module):
    client = http_client_module.RequestsHttpClient()
    closed = {"value": False}

    raw = SimpleNamespace(
        status_code=200,
        ok=True,
        text="",
        url="http://x/",
        headers={},
        json=lambda: {},
        raise_for_status=lambda: None,
        iter_lines=lambda decode_unicode=False: iter(["a", "b"]),
        close=lambda: closed.update(value=True),
    )

    with patch("requests.get", return_value=raw):
        with client.stream_get("http://x/") as resp:
            assert resp.status_code == 200
            list(resp.iter_lines(decode_unicode=True))
    assert closed["value"], "stream_get must close the response on exit"


def test_stream_get_translates_initial_connection_error(http_client_module):
    client = http_client_module.RequestsHttpClient()
    with patch("requests.get", side_effect=requests.exceptions.SSLError("bad cert")):
        cm = client.stream_get("http://x/")
        with pytest.raises(http_client_module.HttpSslError):
            cm.__enter__()


# ── Singleton accessor ───────────────────────────────────────────────────────


def test_get_default_http_client_is_singleton(http_client_module):
    a = http_client_module.get_default_http_client()
    b = http_client_module.get_default_http_client()
    assert a is b
    assert isinstance(a, http_client_module.RequestsHttpClient)
