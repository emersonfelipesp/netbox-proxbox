"""Tests for exact-job E2E sync polling."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest


class _Response:
    def __init__(
        self,
        *,
        status_code: int,
        payload: dict | None = None,
        text: str = "",
        cookies: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text
        self.cookies = cookies or {}
        self.headers = headers or {}
        self.closed = False

    def json(self) -> dict:
        return self._payload

    def iter_content(self, chunk_size: int):
        del chunk_size
        yield json.dumps(self._payload).encode()

    def close(self) -> None:
        self.closed = True


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        self.now += 1.0
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def _load_stack_sync():
    e2e_dir = Path(__file__).resolve().parent / "e2e"
    sys.path.insert(0, str(e2e_dir))
    try:
        sys.modules.pop("stack_common", None)
        sys.modules.pop("stack_sync", None)
        return importlib.import_module("stack_sync")
    finally:
        sys.path.pop(0)


def _trigger_response(*, job_id: str = "42", location: str = "/plugins/proxbox/home/"):
    return _Response(
        status_code=302,
        headers={"Location": location, "X-Proxbox-Job-ID": job_id},
    )


def test_trigger_and_wait_sync_polls_authoritative_job_id(monkeypatch):
    stack_sync = _load_stack_sync()
    clock = _Clock()
    monkeypatch.setattr(stack_sync.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(stack_sync.time, "sleep", clock.sleep)

    requested_urls: list[str] = []
    job_reads = 0

    def fake_get(url: str, **_kwargs):
        nonlocal job_reads
        requested_urls.append(url)
        if url.endswith("/login/"):
            return _Response(status_code=200, cookies={"csrftoken": "csrf-token"})
        if url.endswith("/api/core/jobs/42/"):
            job_reads += 1
            status = "pending" if job_reads == 1 else "completed"
            return _Response(
                status_code=200,
                payload={
                    "id": 42,
                    "name": "Proxbox Sync: Virtual machines",
                    "status": {"value": status, "label": status.title()},
                },
            )
        raise AssertionError(f"Unexpected GET url: {url}")

    monkeypatch.setattr(stack_sync.requests, "get", fake_get)
    monkeypatch.setattr(
        stack_sync.requests,
        "post",
        lambda *_args, **_kwargs: _trigger_response(),
    )

    job = stack_sync.trigger_and_wait_sync(
        "http://netbox.example",
        "token-value",
        route="/plugins/proxbox/sync/virtual-machines/",
        expected_name_fragment="virtual machines",
    )

    assert job["id"] == 42
    assert job["status"]["value"] == "completed"
    assert requested_urls == [
        "http://netbox.example/login/",
        "http://netbox.example/api/core/jobs/42/",
        "http://netbox.example/api/core/jobs/42/",
    ]
    assert clock.sleeps == [5.0]


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (_trigger_response(location=""), "invalid redirect"),
        (_trigger_response(location="/login/?next=/plugins/proxbox/home/"), "outside"),
        (_trigger_response(location="https://attacker.example/"), "invalid redirect"),
        (_trigger_response(location="/plugins/proxbox/"), "outside"),
        (_trigger_response(location="/plugins/proxbox/home"), "outside"),
        (_trigger_response(location="/plugins/proxbox/home////"), "outside"),
        (_trigger_response(location="/plugins/proxbox/home/?"), "outside"),
        (_trigger_response(location="/plugins/proxbox/home/#"), "outside"),
        (_trigger_response(location="/plugins/proxbox/home/?next=/login/"), "outside"),
        (_trigger_response(location="/plugins/proxbox/other/"), "outside"),
        (
            _trigger_response(location="//attacker.example/plugins/proxbox/home/"),
            "invalid redirect",
        ),
        (
            _trigger_response(
                location="http://attacker@netbox.example/plugins/proxbox/home/"
            ),
            "invalid redirect",
        ),
        (_trigger_response(location="/plugins/proxbox/%68ome/"), "outside"),
        (_trigger_response(location="http://[::1"), "invalid redirect"),
        (_trigger_response(job_id=""), "authoritative job ID"),
        (_trigger_response(job_id="0"), "authoritative job ID"),
        (_trigger_response(job_id="٠"), "authoritative job ID"),
        (_trigger_response(job_id="²"), "authoritative job ID"),
        (_trigger_response(job_id="9" * 1000), "authoritative job ID"),
    ],
)
def test_trigger_and_wait_sync_rejects_invalid_trigger_response(
    monkeypatch, response, message
):
    stack_sync = _load_stack_sync()
    monkeypatch.setattr(
        stack_sync.requests,
        "get",
        lambda *_args, **_kwargs: _Response(
            status_code=200,
            cookies={"csrftoken": "csrf-token"},
        ),
    )
    monkeypatch.setattr(
        stack_sync.requests,
        "post",
        lambda *_args, **_kwargs: response,
    )

    with pytest.raises(AssertionError, match=message):
        stack_sync.trigger_and_wait_sync(
            "http://netbox.example",
            "token-value",
            route="/plugins/proxbox/sync/devices/",
            expected_name_fragment="devices",
        )


def test_trigger_and_wait_sync_rejects_mismatched_job_resource(monkeypatch):
    stack_sync = _load_stack_sync()

    def fake_get(url: str, **_kwargs):
        if url.endswith("/login/"):
            return _Response(status_code=200, cookies={"csrftoken": "csrf-token"})
        return _Response(
            status_code=200,
            payload={
                "id": 99,
                "name": "Proxbox Sync: Devices",
                "status": {"value": "completed", "label": "Completed"},
            },
        )

    monkeypatch.setattr(stack_sync.requests, "get", fake_get)
    monkeypatch.setattr(
        stack_sync.requests,
        "post",
        lambda *_args, **_kwargs: _trigger_response(job_id="42"),
    )

    with pytest.raises(AssertionError, match="mismatched job 42"):
        stack_sync.trigger_and_wait_sync(
            "http://netbox.example",
            "token-value",
            route="/plugins/proxbox/sync/devices/",
            expected_name_fragment="devices",
        )


def test_trigger_and_wait_sync_caps_final_sleep_to_deadline(monkeypatch):
    stack_sync = _load_stack_sync()
    clock = _Clock()
    monkeypatch.setattr(stack_sync.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(stack_sync.time, "sleep", clock.sleep)

    def fake_get(url: str, **_kwargs):
        if url.endswith("/login/"):
            return _Response(status_code=200, cookies={"csrftoken": "csrf-token"})
        return _Response(
            status_code=200,
            payload={
                "id": 42,
                "name": "Proxbox Sync: Devices",
                "status": {"value": "pending", "label": "Pending"},
            },
        )

    monkeypatch.setattr(stack_sync.requests, "get", fake_get)
    monkeypatch.setattr(
        stack_sync.requests,
        "post",
        lambda *_args, **_kwargs: _trigger_response(),
    )

    with pytest.raises(AssertionError, match="Timed out waiting"):
        stack_sync.trigger_and_wait_sync(
            "http://netbox.example",
            "token-value",
            route="/plugins/proxbox/sync/devices/",
            expected_name_fragment="devices",
        )

    assert clock.sleeps
    assert max(clock.sleeps) <= 5.0
    assert clock.now <= 602.0


def test_read_json_with_deadline_stops_slow_body(monkeypatch):
    _load_stack_sync()
    stack_common = sys.modules["stack_common"]
    clock = _Clock()
    monkeypatch.setattr(stack_common.time, "monotonic", clock.monotonic)

    response = _Response(status_code=200, payload={"id": 42})

    def slow_content(chunk_size: int):
        del chunk_size
        for _index in range(20):
            clock.sleep(1)
            yield b" "

    response.iter_content = slow_content
    monkeypatch.setattr(
        stack_common.requests,
        "get",
        lambda *_args, **_kwargs: response,
    )

    with pytest.raises(AssertionError, match="wall-clock deadline"):
        stack_common.read_json_with_deadline(
            "http://netbox.example/api/core/jobs/42/",
            {},
            context="read sync job 42",
            deadline=10,
        )
    assert response.closed is True
