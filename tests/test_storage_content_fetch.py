"""Adversarial resource-lifetime tests for storage content HTTP fan-out."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from threading import Event, Lock, enumerate as enumerate_threads
import time
from unittest.mock import patch

import pytest
import requests


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "netbox_proxbox"
    / "views"
    / "storage_content.py"
)
MODULE_NAME = "_netbox_proxbox_storage_content_under_test"


def _load_module():
    spec = importlib.util.spec_from_file_location(MODULE_NAME, MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


storage_content = _load_module()


def _wait_until(predicate, *, timeout: float = 1.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.001)
    assert predicate()


def test_repeated_deadlines_cannot_accumulate_http_workers_or_slots() -> None:
    """Slow calls outliving page requests keep the one process-wide pool full."""
    release = Event()
    lock = Lock()
    active = 0
    maximum_active = 0
    started_calls = 0

    def fake_trickling_http_call(node: str, deadline_at: float) -> str:
        del deadline_at
        nonlocal active, maximum_active, started_calls
        with lock:
            active += 1
            started_calls += 1
            maximum_active = max(maximum_active, active)
        try:
            # This deliberately ignores the caller's deadline, like the old
            # response.json() path receiving bytes often enough to stay alive.
            while not release.wait(0.002):
                pass
            return node
        finally:
            with lock:
                active -= 1

    pool = storage_content._CONTENT_FETCH_POOL
    _wait_until(lambda: pool.slots_in_use == 0)
    try:
        for _ in range(12):
            completed, total_count, selected_count = (
                storage_content.collect_completed_before_deadline(
                    [f"pve-{index}" for index in range(8)],
                    fake_trickling_http_call,
                    deadline_seconds=0.01,
                    max_items=64,
                    per_request_workers=4,
                )
            )
            assert completed == []
            assert total_count == selected_count == 8

        worker_threads = [
            thread
            for thread in enumerate_threads()
            if thread.name.startswith(storage_content.CONTENT_FETCH_THREAD_PREFIX)
        ]
        assert started_calls == storage_content.CONTENT_FETCH_WORKERS
        assert maximum_active == storage_content.CONTENT_FETCH_WORKERS
        assert pool.slots_in_use == storage_content.CONTENT_FETCH_WORKERS
        assert len(worker_threads) <= storage_content.CONTENT_FETCH_WORKERS
    finally:
        release.set()
        _wait_until(lambda: pool.slots_in_use == 0)
        _wait_until(lambda: active == 0)


def test_slot_exhaustion_degrades_to_the_existing_partial_notice() -> None:
    release = Event()
    started = Event()
    started_count = 0
    lock = Lock()

    def occupying_call(node: str, deadline_at: float) -> str:
        del deadline_at
        nonlocal started_count
        with lock:
            started_count += 1
            if started_count == storage_content.CONTENT_FETCH_WORKERS:
                started.set()
        release.wait(timeout=1)
        return node

    pool = storage_content._CONTENT_FETCH_POOL
    _wait_until(lambda: pool.slots_in_use == 0)
    blockers = []
    try:
        deadline_at = time.monotonic() + 1
        for index in range(storage_content.CONTENT_FETCH_WORKERS):
            future = pool.submit(
                occupying_call,
                f"occupied-{index}",
                deadline_at,
                deadline_at=deadline_at,
                wait_for_slot=False,
            )
            assert future is not None
            blockers.append(future)
        assert started.wait(timeout=1)

        unexpected_calls = 0

        def should_not_start(node: str, deadline_at: float) -> str:
            del deadline_at
            nonlocal unexpected_calls
            unexpected_calls += 1
            return node

        completed, total_count, selected_count = (
            storage_content.collect_completed_before_deadline(
                ["pve-a", "pve-b", "pve-c"],
                should_not_start,
                deadline_seconds=0.02,
                max_items=64,
                per_request_workers=4,
            )
        )
        detail = storage_content.format_content_detail(
            successful_nodes=len(completed),
            selected_node_count=selected_count,
            total_node_count=total_count,
            deadline_seconds=0.02,
            request_limit=64,
        )

        assert completed == []
        assert unexpected_calls == 0
        assert detail is not None
        assert "0 of 3 node requests completed" in detail
        assert "0.02-second deadline" in detail
    finally:
        release.set()
        for blocker in blockers:
            blocker.result(timeout=1)
        _wait_until(lambda: pool.slots_in_use == 0)


class _FakeStreamingResponse:
    def __init__(self, chunks) -> None:
        self._chunks = chunks
        self.closed = False
        self.headers: dict[str, str] = {}

    def raise_for_status(self) -> None:
        return None

    def iter_content(self, chunk_size: int):
        assert chunk_size > 0
        yield from self._chunks(self)

    def close(self) -> None:
        self.closed = True


def test_streaming_fetch_aborts_a_slow_trickle_at_the_wall_deadline() -> None:
    yielded_chunks = 0

    def trickle(response: _FakeStreamingResponse):
        nonlocal yielded_chunks
        while not response.closed:
            time.sleep(0.002)
            yielded_chunks += 1
            yield b" "

    response = _FakeStreamingResponse(trickle)
    started_at = time.monotonic()
    with (
        patch.object(storage_content.requests, "get", return_value=response) as get,
        pytest.raises(requests.exceptions.Timeout),
    ):
        storage_content.fetch_json_with_limits(
            url="https://backend.example.test/proxmox/nodes/pve/storage/local/content",
            query_params={"proxmox_endpoint_ids": "11"},
            auth_headers={"X-Proxbox-API-Key": "redacted-test-value"},
            verify_ssl=True,
            request_timeout=1,
            deadline_at=started_at + 0.03,
            max_response_bytes=1024,
        )
    elapsed = time.monotonic() - started_at

    assert elapsed < 0.2
    assert yielded_chunks > 1
    assert response.closed is True
    assert get.call_args.kwargs["stream"] is True
    assert get.call_args.kwargs["allow_redirects"] is False
    deadline_threads = [
        thread
        for thread in enumerate_threads()
        if thread.name == storage_content.CONTENT_DEADLINE_THREAD_NAME
    ]
    assert len(deadline_threads) == 1


def test_streaming_fetch_rejects_an_oversized_response_and_closes_it() -> None:
    def oversized(_response: _FakeStreamingResponse):
        yield b'{"volid":"'
        yield b"x" * 32
        yield b'"}'

    response = _FakeStreamingResponse(oversized)
    with (
        patch.object(storage_content.requests, "get", return_value=response),
        pytest.raises(ValueError, match="exceeds the 16-byte limit"),
    ):
        storage_content.fetch_json_with_limits(
            url="https://backend.example.test/proxmox/nodes/pve/storage/local/content",
            query_params=None,
            auth_headers={"X-Proxbox-API-Key": "redacted-test-value"},
            verify_ssl=True,
            request_timeout=1,
            deadline_at=time.monotonic() + 1,
            max_response_bytes=16,
        )

    assert response.closed is True


def test_streaming_fetch_preserves_the_json_payload_shape() -> None:
    def valid_json(_response: _FakeStreamingResponse):
        yield b'[{"volid":'
        yield b'"local:iso/debian.iso"}]'

    response = _FakeStreamingResponse(valid_json)
    with patch.object(storage_content.requests, "get", return_value=response):
        payload = storage_content.fetch_json_with_limits(
            url="https://backend.example.test/proxmox/nodes/pve/storage/local/content",
            query_params={"proxmox_endpoint_ids": "11"},
            auth_headers={"X-Proxbox-API-Key": "redacted-test-value"},
            verify_ssl=True,
            request_timeout=1,
            deadline_at=time.monotonic() + 1,
            max_response_bytes=1024,
        )

    assert payload == [{"volid": "local:iso/debian.iso"}]
    assert response.closed is True
