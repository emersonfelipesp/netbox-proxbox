"""Tests for test_stack_sync_polling."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path


class _Response:
    def __init__(
        self,
        *,
        status_code: int,
        payload: dict | None = None,
        text: str = "",
        cookies: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text
        self.cookies = cookies or {}

    def json(self) -> dict:
        return self._payload


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def time(self) -> float:
        self.now += 1.0
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def test_trigger_and_wait_sync_accepts_choice_field_status(monkeypatch):
    e2e_dir = Path(__file__).resolve().parent / "e2e"
    sys.path.insert(0, str(e2e_dir))
    try:
        sys.modules.pop("stack_common", None)
        sys.modules.pop("stack_sync", None)
        stack_sync = importlib.import_module("stack_sync")
    finally:
        sys.path.pop(0)

    clock = _Clock()
    monkeypatch.setattr(stack_sync.time, "time", clock.time)
    monkeypatch.setattr(stack_sync.time, "sleep", clock.sleep)
    monkeypatch.setattr(stack_sync, "snapshot_proxbox_job_ids", lambda *_args: set())

    def fake_get(url: str, **_kwargs):
        if url.endswith("/login/"):
            return _Response(status_code=200, cookies={"csrftoken": "csrf-token"})
        if "/api/core/jobs/" in url:
            return _Response(
                status_code=200,
                payload={
                    "results": [
                        {
                            "id": 42,
                            "name": "Proxbox Sync: Devices",
                            "status": {"value": "completed", "label": "Completed"},
                        }
                    ]
                },
            )
        raise AssertionError(f"Unexpected GET url: {url}")

    def fake_post(url: str, **_kwargs):
        if url.endswith("/plugins/proxbox/sync/devices/"):
            return _Response(status_code=302)
        raise AssertionError(f"Unexpected POST url: {url}")

    monkeypatch.setattr(stack_sync.requests, "get", fake_get)
    monkeypatch.setattr(stack_sync.requests, "post", fake_post)

    job = stack_sync.trigger_and_wait_sync(
        "http://netbox.example",
        "token-value",
        route="/plugins/proxbox/sync/devices/",
        expected_name_fragment="devices",
    )

    assert job["id"] == 42
    assert job["status"]["value"] == "completed"
