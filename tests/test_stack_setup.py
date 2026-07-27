"""Tests for test_stack_setup."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest


class _Response:
    def __init__(
        self, *, status_code: int, payload: dict | None = None, text: str = ""
    ):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self) -> dict:
        return self._payload


def _load_stack_setup():
    e2e_dir = Path(__file__).resolve().parent / "e2e"
    sys.path.insert(0, str(e2e_dir))
    try:
        sys.modules.pop("stack_common", None)
        sys.modules.pop("stack_setup", None)
        return importlib.import_module("stack_setup")
    finally:
        sys.path.pop(0)


def test_ensure_proxbox_backend_endpoints_skips_direct_proxmox_seed(monkeypatch):
    stack_setup = _load_stack_setup()

    calls: list[tuple[str, str]] = []

    def fake_post(url: str, **_kwargs):
        calls.append(("POST", url))
        if url.endswith("/netbox/endpoint"):
            return _Response(status_code=200, payload={"id": 1}, text='{"id":1}')
        raise AssertionError(f"Unexpected POST url: {url}")

    def fake_get(url: str, **_kwargs):
        calls.append(("GET", url))
        if url.endswith("/netbox/status"):
            return _Response(status_code=200, payload={"ok": True}, text='{"ok":true}')
        raise AssertionError(f"Unexpected GET url: {url}")

    monkeypatch.setattr(stack_setup.requests, "post", fake_post)
    monkeypatch.setattr(stack_setup.requests, "get", fake_get)

    stack_setup.ensure_proxbox_backend_endpoints(
        "http://proxbox-api.test",
        "http://172.18.0.6:8080",
        "token-value",
    )

    assert calls == [
        ("POST", "http://proxbox-api.test/netbox/endpoint"),
        ("GET", "http://proxbox-api.test/netbox/status"),
    ]


def test_register_proxbox_api_key_bootstraps_only_a_consistent_empty_backend(
    monkeypatch,
):
    stack_setup = _load_stack_setup()
    calls: list[tuple[str, str, dict]] = []

    def fake_get(url: str, **kwargs):
        calls.append(("GET", url, kwargs))
        return _Response(
            status_code=200,
            payload={"needs_bootstrap": True, "has_db_keys": False},
        )

    def fake_post(url: str, **kwargs):
        calls.append(("POST", url, kwargs))
        return _Response(status_code=201, payload={"detail": "registered"})

    monkeypatch.setattr(stack_setup.requests, "get", fake_get)
    monkeypatch.setattr(stack_setup.requests, "post", fake_post)

    result = stack_setup.register_proxbox_api_key("http://proxbox-api.test")

    assert result == stack_setup._E2E_PROXBOX_API_KEY
    assert [method for method, _url, _kwargs in calls] == ["GET", "POST"]
    assert all(kwargs["allow_redirects"] is False for _method, _url, kwargs in calls)


def test_register_proxbox_api_key_authenticates_retained_key_when_initialized(
    monkeypatch,
):
    stack_setup = _load_stack_setup()
    calls: list[tuple[str, dict]] = []

    def fake_get(url: str, **kwargs):
        calls.append((url, kwargs))
        if url.endswith("/auth/bootstrap-status"):
            return _Response(
                status_code=200,
                payload={"needs_bootstrap": False, "has_db_keys": True},
            )
        return _Response(status_code=200, payload={"keys": [{"id": 1}]})

    def unexpected_post(*_args, **_kwargs):
        raise AssertionError("initialized backend must not receive bootstrap POST")

    monkeypatch.setattr(stack_setup.requests, "get", fake_get)
    monkeypatch.setattr(stack_setup.requests, "post", unexpected_post)

    stack_setup.register_proxbox_api_key("http://proxbox-api.test")

    assert len(calls) == 2
    assert calls[1][1]["headers"] == {
        "X-Proxbox-API-Key": stack_setup._E2E_PROXBOX_API_KEY
    }
    assert all(kwargs["allow_redirects"] is False for _url, kwargs in calls)


def test_register_proxbox_api_key_rejects_bootstrap_conflict(monkeypatch):
    stack_setup = _load_stack_setup()

    monkeypatch.setattr(
        stack_setup.requests,
        "get",
        lambda *_args, **_kwargs: _Response(
            status_code=200,
            payload={"needs_bootstrap": True, "has_db_keys": False},
        ),
    )
    monkeypatch.setattr(
        stack_setup.requests,
        "post",
        lambda *_args, **_kwargs: _Response(status_code=409),
    )

    with pytest.raises(AssertionError, match="HTTP 409"):
        stack_setup.register_proxbox_api_key("http://proxbox-api.test")


def test_sensitive_assertion_omits_response_body(monkeypatch):
    stack_setup = _load_stack_setup()
    secret = "replacement-key-that-must-not-reach-ci-output"
    response = _Response(status_code=401, text=f'{{"echo":"{secret}"}}')

    with pytest.raises(AssertionError) as captured:
        stack_setup.assert_ok(
            response,
            context="sensitive auth operation",
            include_response_body=False,
        )

    assert "HTTP 401" in str(captured.value)
    assert secret not in str(captured.value)
