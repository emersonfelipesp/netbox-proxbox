from __future__ import annotations

import importlib
import sys
from pathlib import Path


class _Response:
    def __init__(
        self, *, status_code: int, payload: dict | None = None, text: str = ""
    ):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self) -> dict:
        return self._payload


def test_ensure_proxbox_backend_endpoints_skips_direct_proxmox_seed(monkeypatch):
    e2e_dir = Path(__file__).resolve().parent / "e2e"
    sys.path.insert(0, str(e2e_dir))
    try:
        sys.modules.pop("stack_common", None)
        sys.modules.pop("stack_setup", None)
        stack_setup = importlib.import_module("stack_setup")
    finally:
        sys.path.pop(0)

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
