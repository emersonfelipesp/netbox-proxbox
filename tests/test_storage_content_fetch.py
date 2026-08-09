"""Adversarial resource-lifetime tests for storage content HTTP fan-out."""

from __future__ import annotations

import importlib.util
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
from threading import Event, Lock, Thread, enumerate as enumerate_threads
import time

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


class _DeadlineTestHandler(BaseHTTPRequestHandler):
    """Serve real socket stalls that inactivity timeouts cannot stop."""

    protocol_version = "HTTP/1.1"
    slow_body_started = Event()
    slow_headers_started = Event()

    def log_message(self, format: str, *args: object) -> None:
        del format, args

    def _send_piece(self, piece: bytes) -> bool:
        try:
            self.connection.sendall(piece)
        except OSError:
            return False
        return True

    def do_GET(self) -> None:
        if self.path == "/slow-body":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Connection", "close")
            self.end_headers()
            self.slow_body_started.set()
            while self._send_piece(b" "):
                time.sleep(0.01)
            return

        if self.path == "/slow-headers":
            self.slow_headers_started.set()
            if not self._send_piece(b"HTTP/1.1 200 OK\r\nX-Slow-Header: "):
                return
            while self._send_piece(b"x"):
                time.sleep(0.01)
            return

        if self.path == "/oversized":
            body = b'{"volid":"' + (b"x" * 32) + b'"}'
        else:
            body = b'[{"volid":"local:iso/debian.iso"}]'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture(scope="module")
def deadline_test_server() -> str:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _DeadlineTestHandler)
    server.daemon_threads = True
    host, port = server.server_address
    assert host == "127.0.0.1"
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)


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


@pytest.mark.parametrize(
    ("route", "started_event"),
    [
        ("/slow-body", _DeadlineTestHandler.slow_body_started),
        ("/slow-headers", _DeadlineTestHandler.slow_headers_started),
    ],
)
def test_real_socket_stalls_release_every_slot_and_allow_recovery(
    deadline_test_server: str,
    route: str,
    started_event: Event,
) -> None:
    """A body or header trickle must not outlive one absolute page deadline."""
    pool = storage_content._CONTENT_FETCH_POOL
    _wait_until(lambda: pool.slots_in_use == 0)
    started_event.clear()
    deadline_seconds = 0.25

    def fetch_stalled(_node: object, deadline_at: float) -> object:
        return storage_content.fetch_json_with_limits(
            url=f"{deadline_test_server}{route}",
            query_params=None,
            auth_headers={"X-Proxbox-API-Key": "redacted-test-value"},
            verify_ssl=True,
            request_timeout=1,
            deadline_at=deadline_at,
            max_response_bytes=1024,
        )

    started_at = time.monotonic()
    completed, total_count, selected_count = (
        storage_content.collect_completed_before_deadline(
            [f"pve-{index}" for index in range(storage_content.CONTENT_FETCH_WORKERS)],
            fetch_stalled,
            deadline_seconds=deadline_seconds,
            max_items=64,
            per_request_workers=storage_content.CONTENT_FETCH_WORKERS,
        )
    )
    elapsed = time.monotonic() - started_at

    assert started_event.is_set()
    assert total_count == selected_count == storage_content.CONTENT_FETCH_WORKERS
    assert all(future.exception() is not None for future in completed)
    assert deadline_seconds * 0.7 <= elapsed < deadline_seconds + 0.75
    _wait_until(lambda: pool.slots_in_use == 0, timeout=1)

    def fetch_healthy(_node: object, deadline_at: float) -> object:
        return storage_content.fetch_json_with_limits(
            url=f"{deadline_test_server}/success",
            query_params=None,
            auth_headers={"X-Proxbox-API-Key": "redacted-test-value"},
            verify_ssl=True,
            request_timeout=1,
            deadline_at=deadline_at,
            max_response_bytes=1024,
        )

    recovered, recovery_total, recovery_selected = (
        storage_content.collect_completed_before_deadline(
            ["pve-recovered"],
            fetch_healthy,
            deadline_seconds=1,
            max_items=64,
            per_request_workers=storage_content.CONTENT_FETCH_WORKERS,
        )
    )
    assert recovery_total == recovery_selected == 1
    assert len(recovered) == 1
    assert recovered[0].result() == [{"volid": "local:iso/debian.iso"}]
    assert pool.slots_in_use == 0

    deadline_threads = [
        thread
        for thread in enumerate_threads()
        if thread.name == storage_content.CONTENT_DEADLINE_THREAD_NAME
    ]
    assert len(deadline_threads) == 1


def test_streaming_fetch_rejects_an_oversized_response(
    deadline_test_server: str,
) -> None:
    with pytest.raises(ValueError, match="exceeds the 16-byte limit"):
        storage_content.fetch_json_with_limits(
            url=f"{deadline_test_server}/oversized",
            query_params=None,
            auth_headers={"X-Proxbox-API-Key": "redacted-test-value"},
            verify_ssl=True,
            request_timeout=1,
            deadline_at=time.monotonic() + 1,
            max_response_bytes=16,
        )


def test_streaming_fetch_preserves_the_json_payload_shape(
    deadline_test_server: str,
) -> None:
    payload = storage_content.fetch_json_with_limits(
        url=f"{deadline_test_server}/success",
        query_params={"proxmox_endpoint_ids": "11"},
        auth_headers={"X-Proxbox-API-Key": "redacted-test-value"},
        verify_ssl=True,
        request_timeout=1,
        deadline_at=time.monotonic() + 1,
        max_response_bytes=1024,
    )

    assert payload == [{"volid": "local:iso/debian.iso"}]
