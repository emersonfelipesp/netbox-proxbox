"""Focused mocked tests for WebSocket command and terminal correlation."""

from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path
import sys
import threading
from types import ModuleType, SimpleNamespace
from typing import Callable

import pytest

from tests.conftest import load_plugin_module


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "netbox_proxbox" / "websocket_client.py"


@pytest.fixture
def websocket_module(monkeypatch, fastapi_endpoint):
    fastapi_endpoint.pk = fastapi_endpoint.id
    fastapi_endpoint.enabled = True
    fastapi_endpoint.server_side_websocket = True
    fastapi_endpoint.backend_key_target_fingerprint = "trusted-target"
    detail = {
        "http_url": "https://backend.example.test:8800",
        "server_websocket_url": "wss://backend.example.test:8801/ws",
        "verify_ssl": True,
    }
    load_plugin_module(
        "netbox_proxbox.views.keepalive_status",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
        get_fastapi_url=lambda _endpoint: detail,
    )
    asgiref = ModuleType("asgiref")
    asgiref_sync = ModuleType("asgiref.sync")

    def sync_to_async(
        function: Callable[..., object], **_kwargs: object
    ) -> Callable[..., object]:
        async def call(*args: object, **kwargs: object) -> object:
            return function(*args, **kwargs)

        return call

    asgiref_sync.sync_to_async = sync_to_async
    monkeypatch.setitem(sys.modules, "asgiref", asgiref)
    monkeypatch.setitem(sys.modules, "asgiref.sync", asgiref_sync)
    sys.modules.pop("netbox_proxbox.websocket_client", None)
    spec = importlib.util.spec_from_file_location(
        "netbox_proxbox.websocket_client", MODULE_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    yield module

    while not module.message_queue.empty():
        module.message_queue.get_nowait()
    module.GLOBAL_WEBSOCKET_MESSAGES.clear()
    module._ws_capability_cache.clear()


def _reset_state(module, *, active: str, run_id: str | None) -> None:
    for kind in module.ws_sync_button_state:
        module.ws_sync_button_state[kind] = (
            "syncing" if kind == active else "not-started"
        )
        module.ws_sync_run_id[kind] = run_id if kind == active else None


def _response(payload: object, status_code: int = 200) -> SimpleNamespace:
    return SimpleNamespace(status_code=status_code, json=lambda: payload)


def test_capability_probe_uses_remaining_deadline_for_each_request(
    websocket_module, monkeypatch
) -> None:
    credentials = websocket_module._load_websocket_credentials(1)
    assert credentials is not None
    clock = iter((100.0, 100.25, 101.75, 103.0))
    calls: list[tuple[str, dict[str, object]]] = []

    def get(url: str, **kwargs: object) -> SimpleNamespace:
        calls.append((url, kwargs))
        return _response({"status": "ready"})

    monkeypatch.setattr(websocket_module.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(websocket_module.requests, "get", get)

    assert websocket_module._probe_backend_ws_run_id(1, credentials.identity) is False
    assert calls == [
        (
            "https://backend.example.test:8800",
            {"headers": {}, "verify": True, "timeout": 2.75, "allow_redirects": False},
        ),
        (
            "https://backend.example.test:8800/health",
            {
                "headers": credentials.auth_headers,
                "verify": True,
                "timeout": 1.25,
                "allow_redirects": False,
            },
        ),
    ]


def test_capability_probe_preserves_minimum_positive_timeout(
    websocket_module, monkeypatch
) -> None:
    credentials = websocket_module._load_websocket_credentials(1)
    assert credentials is not None
    clock = iter((100.0, 102.9995))
    calls: list[dict[str, object]] = []

    def get(_url: str, **kwargs: object) -> SimpleNamespace:
        calls.append(kwargs)
        return _response({"capabilities": {"ws_run_id": 1}})

    monkeypatch.setattr(websocket_module.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(websocket_module.requests, "get", get)

    assert websocket_module._probe_backend_ws_run_id(1, credentials.identity) is True
    assert calls == [
        {"headers": {}, "verify": True, "timeout": 0.001, "allow_redirects": False}
    ]


@pytest.mark.parametrize("request_time", [103.0, 103.5])
def test_capability_probe_stops_when_deadline_is_exhausted(
    websocket_module, monkeypatch, request_time: float
) -> None:
    credentials = websocket_module._load_websocket_credentials(1)
    assert credentials is not None
    clock = iter((100.0, request_time))
    calls: list[str] = []

    def get(url: str, **_kwargs: object) -> SimpleNamespace:
        calls.append(url)
        return _response({"capabilities": {"ws_run_id": 1}})

    monkeypatch.setattr(websocket_module.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(websocket_module.requests, "get", get)

    assert websocket_module._probe_backend_ws_run_id(1, credentials.identity) is False
    assert calls == []


@pytest.mark.parametrize(
    ("fallback_time", "expected_timeouts", "supported"),
    [(101.5, [2.75, 1.5], True), (103.5, [2.75], False)],
)
def test_capability_probe_timeout_error_retains_remaining_budget(
    websocket_module,
    monkeypatch,
    fallback_time: float,
    expected_timeouts: list[float],
    supported: bool,
) -> None:
    credentials = websocket_module._load_websocket_credentials(1)
    assert credentials is not None
    clock = iter((100.0, 100.25, fallback_time))
    calls: list[tuple[str, dict[str, object]]] = []
    timeout_error = websocket_module.requests.Timeout("Synthetic capability timeout")

    def get(url: str, **kwargs: object) -> SimpleNamespace:
        calls.append((url, kwargs))
        if len(calls) == 1:
            raise timeout_error
        return _response({"capabilities": {"ws_run_id": 1}})

    monkeypatch.setattr(websocket_module.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(websocket_module.requests, "get", get)

    assert (
        websocket_module._probe_backend_ws_run_id(1, credentials.identity) is supported
    )
    assert [kwargs["timeout"] for _url, kwargs in calls] == expected_timeouts
    assert calls[0] == (
        "https://backend.example.test:8800",
        {"headers": {}, "verify": True, "timeout": 2.75, "allow_redirects": False},
    )
    if supported:
        assert calls[1] == (
            "https://backend.example.test:8800/health",
            {
                "headers": credentials.auth_headers,
                "verify": True,
                "timeout": 1.5,
                "allow_redirects": False,
            },
        )


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"capabilities": {"ws_run_id": 1}}, True),
        ({"capabilities": {"ws_run_id": True}}, False),
        ({"capabilities": {"ws_run_id": 1.0}}, False),
        ({"capabilities": {}}, False),
        ({"capabilities": []}, False),
    ],
)
def test_run_id_capability_requires_exact_integer_v1(
    websocket_module, payload: object, expected: bool
) -> None:
    assert websocket_module._payload_supports_ws_run_id(payload) is expected


def test_capability_absent_sends_the_legacy_bare_command(
    websocket_module, monkeypatch
) -> None:
    calls: list[str] = []

    def get(url: str, **_kwargs: object) -> SimpleNamespace:
        calls.append(url)
        return _response({"status": "ready"})

    monkeypatch.setattr(websocket_module.requests, "get", get)
    credentials = websocket_module._load_websocket_credentials(1)
    assert credentials is not None

    connection_id = websocket_module._open_connection_session(
        1,
        credentials.identity,
    )
    supported = websocket_module._backend_supports_ws_run_id(
        1, credentials.identity, connection_id
    )
    run_id = websocket_module.send_message(
        "Sync Nodes",
        endpoint_id=1,
        identity=credentials.identity,
        use_run_id=supported,
        connection_id=connection_id,
    )
    queued = websocket_module.message_queue.get_nowait()

    assert supported is False
    assert run_id is None
    assert (
        websocket_module._command_for_worker(
            queued,
            1,
            credentials.identity,
            connection_id=connection_id,
            supports_run_id=supported,
        )
        == "Sync Nodes"
    )
    assert calls == [
        "https://backend.example.test:8800",
        "https://backend.example.test:8800/health",
        "https://backend.example.test:8800/version",
    ]


def test_capability_present_sends_a_run_id_envelope_and_is_cached(
    websocket_module, monkeypatch
) -> None:
    calls: list[str] = []
    health_headers: dict[str, str] = {}

    def get(url: str, **kwargs: object) -> SimpleNamespace:
        calls.append(url)
        if url.endswith("/health"):
            health_headers.update(kwargs["headers"])
            return _response({"capabilities": {"ws_run_id": 1}})
        return _response({"message": "Proxbox Backend"})

    monkeypatch.setattr(websocket_module.requests, "get", get)
    credentials = websocket_module._load_websocket_credentials(1)
    assert credentials is not None

    connection_id = websocket_module._open_connection_session(
        1,
        credentials.identity,
    )
    first = websocket_module._backend_supports_ws_run_id(
        1, credentials.identity, connection_id
    )
    second = websocket_module._backend_supports_ws_run_id(
        1, credentials.identity, connection_id
    )
    run_id = websocket_module.send_message(
        "Full Update",
        endpoint_id=1,
        identity=credentials.identity,
        use_run_id=first,
        connection_id=connection_id,
    )
    queued = websocket_module.message_queue.get_nowait()
    frame = websocket_module._command_for_worker(
        queued,
        1,
        credentials.identity,
        connection_id=connection_id,
        supports_run_id=first,
    )

    assert first is True
    assert second is True
    assert calls == [
        "https://backend.example.test:8800",
        "https://backend.example.test:8800/health",
    ]
    assert health_headers == {"Authorization": "Bearer backend-token"}
    assert run_id is not None
    assert 8 <= len(run_id) <= 64
    assert json.loads(frame) == {"command": "Full Update", "run_id": run_id}


def test_reconnect_invalidates_positive_capability_for_the_same_backend(
    websocket_module, monkeypatch
) -> None:
    decisions = iter((True, False))
    calls = 0

    def probe(_endpoint_id: int, _identity: str) -> bool:
        nonlocal calls
        calls += 1
        return next(decisions)

    monkeypatch.setattr(websocket_module, "_probe_backend_ws_run_id", probe)
    first_connection = websocket_module._open_connection_session(1, "identity")
    assert websocket_module._backend_supports_ws_run_id(1, "identity", first_connection)
    first_key = (1, "identity", first_connection)
    assert first_key in websocket_module._ws_capability_cache

    websocket_module._close_connection_session(1, "identity", first_connection)
    assert first_key not in websocket_module._ws_capability_cache
    second_connection = websocket_module._open_connection_session(1, "identity")

    assert not websocket_module._backend_supports_ws_run_id(
        1, "identity", second_connection
    )
    assert calls == 2


def test_envelope_rejection_stays_negative_for_the_connection(
    websocket_module, monkeypatch
) -> None:
    connection_id = websocket_module._open_connection_session(1, "identity")
    websocket_module._mark_connection_capability_negative(
        1,
        "identity",
        connection_id,
    )

    def unexpected_probe(_endpoint_id: int, _identity: str) -> bool:
        raise AssertionError("a rejected connection must not be probed again")

    monkeypatch.setattr(
        websocket_module,
        "_probe_backend_ws_run_id",
        unexpected_probe,
    )

    assert not websocket_module._backend_supports_ws_run_id(
        1,
        "identity",
        connection_id,
        refresh=True,
    )
    websocket_module._close_connection_session(1, "identity", connection_id)
    assert (1, "identity", connection_id) not in websocket_module._ws_capability_cache


def test_envelope_rejection_wins_over_an_in_flight_positive_probe(
    websocket_module, monkeypatch
) -> None:
    connection_id = websocket_module._open_connection_session(1, "identity")
    probe_started = threading.Event()
    release_probe = threading.Event()
    decisions: list[bool] = []

    def paused_probe(_endpoint_id: int, _identity: str) -> bool:
        probe_started.set()
        assert release_probe.wait(timeout=2)
        return True

    monkeypatch.setattr(websocket_module, "_probe_backend_ws_run_id", paused_probe)
    worker = threading.Thread(
        target=lambda: decisions.append(
            websocket_module._backend_supports_ws_run_id(
                1,
                "identity",
                connection_id,
                refresh=True,
            )
        )
    )
    worker.start()
    assert probe_started.wait(timeout=2)

    websocket_module._mark_connection_capability_negative(
        1,
        "identity",
        connection_id,
    )
    release_probe.set()
    worker.join(timeout=2)

    assert not worker.is_alive()
    assert decisions == [False]
    assert websocket_module._ws_capability_cache[(1, "identity", connection_id)] == (
        websocket_module._WS_REJECTED_CAPABILITY_EXPIRY,
        False,
    )


def test_dispatch_refresh_downgrades_a_cached_positive_after_backend_rollback(
    websocket_module, monkeypatch
) -> None:
    decisions = iter((True, False))
    calls = 0

    def probe(_endpoint_id: int, _identity: str) -> bool:
        nonlocal calls
        calls += 1
        return next(decisions)

    async def credentials(_endpoint_id: int, _identity: str) -> object:
        return object()

    monkeypatch.setattr(websocket_module, "_probe_backend_ws_run_id", probe)
    monkeypatch.setattr(websocket_module, "_reload_credentials", credentials)
    connection_id = websocket_module._open_connection_session(1, "identity")
    assert websocket_module._backend_supports_ws_run_id(1, "identity", connection_id)
    run_id = websocket_module.send_message(
        "Sync Nodes",
        endpoint_id=1,
        identity="identity",
        use_run_id=True,
        connection_id=connection_id,
    )
    assert run_id is not None
    _reset_state(websocket_module, active="devices", run_id=run_id)
    queued = websocket_module.message_queue.get_nowait()

    frame, pending = asyncio.run(
        websocket_module._dispatch_queued_command(queued, 1, "identity", connection_id)
    )

    assert frame == "Sync Nodes"
    assert pending is None
    assert calls == 2
    assert websocket_module.ws_sync_run_id["devices"] is None
    control = json.loads(websocket_module.GLOBAL_WEBSOCKET_MESSAGES[-1][2])
    assert control == {
        "object": "sync-run",
        "run_id": run_id,
        "correlated": False,
    }


def test_expired_queued_correlation_is_reformatted_for_replacement_connection(
    websocket_module,
) -> None:
    run_id = "expired_run_123"
    queued = websocket_module.QueuedCommand(
        endpoint_id=1,
        identity="identity",
        command="Full Update",
        run_id=run_id,
        connection_id="old-connection",
    )
    _reset_state(websocket_module, active="full-update", run_id=run_id)

    frame = websocket_module._command_for_worker(
        queued,
        1,
        "identity",
        connection_id="new-connection",
        supports_run_id=False,
    )

    assert frame == "Full Update"
    assert websocket_module.ws_sync_run_id["full-update"] is None


def test_legacy_command_stays_legacy_on_a_capable_connection(websocket_module) -> None:
    queued = websocket_module.QueuedCommand(
        endpoint_id=1,
        identity="identity",
        command="Sync Nodes",
        connection_id="older-connection",
    )

    frame = websocket_module._command_for_worker(
        queued,
        1,
        "identity",
        connection_id="capable-connection",
        supports_run_id=True,
    )

    assert frame == "Sync Nodes"


def test_correlated_run_ignores_missing_and_mismatched_terminals(
    websocket_module, caplog
) -> None:
    run_id = "device_run_123"
    _reset_state(websocket_module, active="devices", run_id=run_id)
    websocket_module._last_sync_activity = 123.0
    caplog.set_level("DEBUG")

    websocket_module.publish_backend_message(
        '{"object":"device","end":true}', endpoint_id=1
    )
    websocket_module.publish_backend_message(
        '{"object":"device","end":true,"run_id":"other_run_456"}',
        endpoint_id=1,
    )

    assert websocket_module.ws_sync_button_state["devices"] == "syncing"
    assert websocket_module._last_sync_activity == 123.0
    assert "Not attributing WebSocket message to correlated run(s)" in caplog.text

    websocket_module.publish_backend_message(
        json.dumps({"object": "device", "end": True, "run_id": run_id}),
        endpoint_id=1,
    )

    assert websocket_module.ws_sync_button_state["devices"] == "not-started"
    assert websocket_module.ws_sync_run_id["devices"] is None
    assert websocket_module._last_sync_activity > 123.0


def test_correlated_full_update_waits_for_aggregate_with_skipped_stage(
    websocket_module,
) -> None:
    run_id = "full_run_123"
    _reset_state(websocket_module, active="full-update", run_id=run_id)

    websocket_module.publish_backend_message(
        json.dumps({"object": "virtual_machine", "end": True, "run_id": run_id}),
        endpoint_id=1,
    )
    assert websocket_module.ws_sync_button_state["full-update"] == "syncing"

    websocket_module.publish_backend_message(
        json.dumps(
            {
                "object": "full-update",
                "end": True,
                "run_id": run_id,
                "status": "completed",
                "stages": {
                    "devices": "completed",
                    "virtual-machines": "skipped",
                },
            }
        ),
        endpoint_id=1,
    )

    assert websocket_module.ws_sync_button_state["full-update"] == "not-started"
    assert websocket_module.ws_sync_run_id["full-update"] is None


def test_correlated_failed_aggregate_is_terminal(websocket_module) -> None:
    run_id = "failed_run_123"
    _reset_state(websocket_module, active="full-update", run_id=run_id)

    websocket_module.publish_backend_message(
        json.dumps(
            {
                "object": "full-update",
                "end": True,
                "run_id": run_id,
                "status": "failed",
                "stages": {"virtual-machines": "failed"},
            }
        ),
        endpoint_id=1,
    )

    assert websocket_module.ws_sync_button_state["full-update"] == "not-started"


def test_legacy_vm_terminal_still_completes_a_full_update(websocket_module) -> None:
    _reset_state(websocket_module, active="full-update", run_id=None)

    websocket_module.publish_backend_message(
        '{"object":"virtual_machine","end":true}', endpoint_id=1
    )

    assert websocket_module.ws_sync_button_state["full-update"] == "not-started"


class _ScriptedWebSocket:
    def __init__(self, responses: list[str]) -> None:
        self.responses = iter(responses)
        self.sent: list[str] = []

    async def send(self, message: str) -> None:
        self.sent.append(message)

    async def recv(self) -> str:
        try:
            return next(self.responses)
        except StopIteration as exc:
            raise asyncio.CancelledError from exc


class _BlockingWebSocket:
    def __init__(self) -> None:
        self.sent: list[str] = []
        self.sent_event = asyncio.Event()

    async def send(self, message: str) -> None:
        self.sent.append(message)
        self.sent_event.set()

    async def recv(self) -> str:
        await asyncio.Future()
        raise AssertionError("unreachable")


def _queued_correlated_device_run(websocket_module, connection_id: str) -> str:
    run_id = websocket_module.send_message(
        "Sync Nodes",
        endpoint_id=1,
        identity="identity",
        use_run_id=True,
        connection_id=connection_id,
    )
    assert run_id is not None
    _reset_state(websocket_module, active="devices", run_id=run_id)
    return run_id


def _assert_trust_failure(websocket_module, run_id: str) -> None:
    assert websocket_module.ws_sync_button_state["devices"] == "not-started"
    assert websocket_module.ws_sync_run_id["devices"] is None
    payload = json.loads(websocket_module.GLOBAL_WEBSOCKET_MESSAGES[-1][2])
    assert payload == {
        "object": "sync-run",
        "end": True,
        "status": "failed",
        "kind": "devices",
        "error": "WebSocket endpoint trust changed before transmission.",
        "run_id": run_id,
    }


def test_trust_loss_during_capability_discovery_sends_no_command(
    websocket_module, monkeypatch
) -> None:
    connection_id = "discovery-connection"
    run_id = _queued_correlated_device_run(websocket_module, connection_id)
    reloads = iter((object(), None))

    async def credentials(_endpoint_id: int, _identity: str) -> object | None:
        return next(reloads)

    monkeypatch.setattr(websocket_module, "_reload_credentials", credentials)
    monkeypatch.setattr(
        websocket_module,
        "_backend_supports_ws_run_id",
        lambda *_args, **_kwargs: True,
    )
    websocket = _ScriptedWebSocket([])

    with pytest.raises(websocket_module._WebSocketTrustLost):
        asyncio.run(
            websocket_module._run_connected_session(
                websocket,
                1,
                "identity",
                connection_id,
            )
        )

    assert websocket.sent == []
    _assert_trust_failure(websocket_module, run_id)


def test_trust_loss_before_rejection_retry_sends_no_legacy_command(
    websocket_module, monkeypatch
) -> None:
    connection_id = "rejection-connection"
    run_id = _queued_correlated_device_run(websocket_module, connection_id)
    reloads = iter((object(), object(), None))

    async def credentials(_endpoint_id: int, _identity: str) -> object | None:
        return next(reloads)

    monkeypatch.setattr(websocket_module, "_reload_credentials", credentials)
    monkeypatch.setattr(
        websocket_module,
        "_backend_supports_ws_run_id",
        lambda *_args, **_kwargs: True,
    )
    websocket = _ScriptedWebSocket(["Invalid sync command"])

    with pytest.raises(websocket_module._WebSocketTrustLost):
        asyncio.run(
            websocket_module._run_connected_session(
                websocket,
                1,
                "identity",
                connection_id,
            )
        )

    assert len(websocket.sent) == 1
    assert json.loads(websocket.sent[0]) == {
        "command": "Sync Nodes",
        "run_id": run_id,
    }
    assert (1, "identity", connection_id) not in websocket_module._ws_capability_cache
    _assert_trust_failure(websocket_module, run_id)


def test_session_retires_expired_pending_envelope_and_dispatches_successor(
    websocket_module, monkeypatch
) -> None:
    connection_id = "live-connection"
    monkeypatch.setattr(
        websocket_module,
        "websocket_task_identity",
        (1, "identity"),
    )
    monkeypatch.setattr(
        websocket_module,
        "websocket_connection_identity",
        (1, "identity", connection_id),
    )
    monkeypatch.setattr(websocket_module, "_WS_RUNTIME_RECHECK_SEC", 0.01)
    monkeypatch.setattr(
        websocket_module,
        "_backend_supports_ws_run_id",
        lambda *_args, **_kwargs: True,
    )
    monkeypatch.setattr(
        websocket_module.WebSocketView,
        "_ensure_worker",
        lambda _self, _request: (1, None),
    )

    async def credentials(_endpoint_id: int, _identity: str) -> object:
        return object()

    monkeypatch.setattr(websocket_module, "_reload_credentials", credentials)
    request = SimpleNamespace(user=SimpleNamespace(has_perm=lambda _permission: True))
    first = websocket_module.WebSocketView().post(request, "devices")
    first_run_id = first.json()["run_id"]
    websocket = _BlockingWebSocket()

    async def exercise() -> object:
        task = asyncio.create_task(
            websocket_module._run_connected_session(
                websocket,
                1,
                "identity",
                connection_id,
            )
        )
        try:
            await asyncio.wait_for(websocket.sent_event.wait(), timeout=1)
            websocket.sent_event.clear()
            websocket_module._last_sync_activity = (
                websocket_module.time.monotonic()
                - websocket_module.SYNC_LATCH_IDLE_TIMEOUT_SEC
                - 1
            )
            second = websocket_module.WebSocketView().post(request, "devices")
            await asyncio.wait_for(websocket.sent_event.wait(), timeout=1)
            return second
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

    second = asyncio.run(exercise())
    second_run_id = second.json()["run_id"]

    assert first.status_code == 202
    assert second.status_code == 202
    assert second_run_id != first_run_id
    assert [json.loads(frame)["run_id"] for frame in websocket.sent] == [
        first_run_id,
        second_run_id,
    ]
    assert websocket_module.message_queue.empty()
    assert websocket_module.ws_sync_button_state["devices"] == "syncing"
    assert websocket_module.ws_sync_run_id["devices"] == second_run_id


@pytest.mark.parametrize("tagged", [False, True])
def test_envelope_rejection_retries_same_command_once_as_legacy(
    websocket_module, monkeypatch, tagged: bool
) -> None:
    connection_id = "retry-connection"
    run_id = websocket_module.send_message(
        "Sync Nodes",
        endpoint_id=1,
        identity="identity",
        use_run_id=True,
        connection_id=connection_id,
    )
    assert run_id is not None
    _reset_state(websocket_module, active="devices", run_id=run_id)

    async def credentials(_endpoint_id: int, _identity: str) -> object:
        return object()

    monkeypatch.setattr(websocket_module, "_reload_credentials", credentials)
    monkeypatch.setattr(
        websocket_module,
        "_backend_supports_ws_run_id",
        lambda *_args, **_kwargs: True,
    )
    rejection = (
        json.dumps({"message": "Invalid sync command", "run_id": run_id})
        if tagged
        else "Invalid sync command"
    )
    websocket = _ScriptedWebSocket(
        [
            rejection,
            '{"object":"device","end":true}',
        ]
    )

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(
            websocket_module._run_connected_session(
                websocket, 1, "identity", connection_id
            )
        )

    assert json.loads(websocket.sent[0]) == {
        "command": "Sync Nodes",
        "run_id": run_id,
    }
    assert websocket.sent[1:] == ["Sync Nodes"]
    assert (
        websocket_module._ws_capability_cache[(1, "identity", connection_id)][1]
        is False
    )
    buffered = [
        json.loads(message)
        for _sequence, _endpoint, message in websocket_module.GLOBAL_WEBSOCKET_MESSAGES
    ]
    assert buffered == [
        {"object": "sync-run", "run_id": run_id, "correlated": False},
        {"object": "device", "end": True},
    ]
    assert websocket_module.ws_sync_button_state["devices"] == "not-started"
    assert websocket_module.ws_sync_run_id["devices"] is None


def test_capable_http_with_legacy_websocket_peer_stays_legacy_after_rejection(
    websocket_module, monkeypatch
) -> None:
    connection_id = websocket_module._open_connection_session(1, "identity")
    probes = 0

    def capable_probe(_endpoint_id: int, _identity: str) -> bool:
        nonlocal probes
        probes += 1
        return True

    async def credentials(_endpoint_id: int, _identity: str) -> object:
        return object()

    monkeypatch.setattr(websocket_module, "_probe_backend_ws_run_id", capable_probe)
    monkeypatch.setattr(websocket_module, "_reload_credentials", credentials)
    assert websocket_module._backend_supports_ws_run_id(
        1,
        "identity",
        connection_id,
    )
    first_run_id = _queued_correlated_device_run(websocket_module, connection_id)
    first = websocket_module.message_queue.get_nowait()
    first_frame, pending = asyncio.run(
        websocket_module._dispatch_queued_command(
            first,
            1,
            "identity",
            connection_id,
        )
    )
    assert pending is not None
    websocket = _ScriptedWebSocket([])
    asyncio.run(websocket.send(first_frame))
    pending = asyncio.run(
        websocket_module._handle_connected_response(
            websocket,
            "Invalid sync command",
            pending,
            1,
            "identity",
            connection_id,
        )
    )
    websocket_module.publish_backend_message(
        '{"object":"device","end":true}',
        endpoint_id=1,
    )

    assert pending is None
    assert websocket.sent.count("Sync Nodes") == 1
    assert json.loads(websocket.sent[0]) == {
        "command": "Sync Nodes",
        "run_id": first_run_id,
    }
    assert not websocket_module._backend_supports_ws_run_id(
        1,
        "identity",
        connection_id,
        refresh=True,
    )

    second_run_id = websocket_module.send_message(
        "Sync Virtual Machines",
        endpoint_id=1,
        identity="identity",
        use_run_id=False,
        connection_id=connection_id,
    )
    assert second_run_id is None
    _reset_state(websocket_module, active="virtual-machines", run_id=None)
    second = websocket_module.message_queue.get_nowait()
    second_frame, second_pending = asyncio.run(
        websocket_module._dispatch_queued_command(
            second,
            1,
            "identity",
            connection_id,
        )
    )
    asyncio.run(websocket.send(second_frame))

    assert second_pending is None
    assert websocket.sent[1:] == ["Sync Nodes", "Sync Virtual Machines"]
    assert probes == 2


@pytest.mark.parametrize(
    "rejection_payload",
    [
        {"message": "Invalid sync command", "run_id": "foreign_run_456"},
        {"message": "Invalid sync command", "run_id": []},
        {"message": "Invalid sync command", "run_id": {}},
        {"message": "Invalid sync command", "run_id": 7},
        {"message": "Invalid sync command", "run_id": None},
        {"message": "Invalid sync command"},
    ],
)
def test_unattributable_rejection_does_not_replay_before_late_success(
    websocket_module, rejection_payload: dict[str, object]
) -> None:
    run_id = "local_run_123"
    pending = websocket_module.QueuedCommand(
        endpoint_id=1,
        identity="identity",
        command="Sync Nodes",
        run_id=run_id,
        connection_id="connection",
    )
    _reset_state(websocket_module, active="devices", run_id=run_id)
    websocket = _ScriptedWebSocket([])
    rejection = json.dumps(rejection_payload)

    pending = asyncio.run(
        websocket_module._handle_connected_response(
            websocket,
            rejection,
            pending,
            1,
            "identity",
            "connection",
        )
    )
    pending = asyncio.run(
        websocket_module._handle_connected_response(
            websocket,
            json.dumps({"object": "device", "end": True, "run_id": run_id}),
            pending,
            1,
            "identity",
            "connection",
        )
    )

    assert pending is None
    assert websocket.sent == []
    assert websocket_module.ws_sync_button_state["devices"] == "not-started"
    assert (1, "identity", "connection") not in websocket_module._ws_capability_cache


def test_plain_rejection_after_matching_progress_does_not_replay(
    websocket_module,
) -> None:
    run_id = "local_run_123"
    pending = websocket_module.QueuedCommand(
        endpoint_id=1,
        identity="identity",
        command="Sync Nodes",
        run_id=run_id,
        connection_id="connection",
    )
    _reset_state(websocket_module, active="devices", run_id=run_id)
    websocket = _ScriptedWebSocket([])

    pending = asyncio.run(
        websocket_module._handle_connected_response(
            websocket,
            json.dumps({"object": "device", "end": False, "run_id": run_id}),
            pending,
            1,
            "identity",
            "connection",
        )
    )
    pending = asyncio.run(
        websocket_module._handle_connected_response(
            websocket,
            "Invalid sync command",
            pending,
            1,
            "identity",
            "connection",
        )
    )

    assert pending is None
    assert websocket.sent == []
    assert websocket_module.ws_sync_button_state["devices"] == "syncing"
    assert (1, "identity", "connection") not in websocket_module._ws_capability_cache


def test_malformed_run_ids_and_statuses_do_not_interrupt_the_connection(
    websocket_module,
) -> None:
    run_id = "full_run_123"
    _reset_state(websocket_module, active="full-update", run_id=run_id)
    malformed_run_ids = ([], {}, 7, None)
    malformed_statuses = ([], {}, 7, None)
    responses = [
        json.dumps(
            {
                "object": "full-update",
                "end": True,
                "run_id": malformed,
                "status": "completed",
            }
        )
        for malformed in malformed_run_ids
    ]
    responses.extend(
        json.dumps(
            {
                "object": "full-update",
                "end": True,
                "run_id": run_id,
                "status": malformed,
            }
        )
        for malformed in malformed_statuses
    )
    responses.append(
        json.dumps(
            {
                "object": "full-update",
                "end": True,
                "run_id": run_id,
                "status": "completed",
                "stages": {"virtual-machines": "skipped"},
            }
        )
    )
    websocket_module._last_sync_activity = 10.0
    for response in responses[:-1]:
        websocket_module.publish_backend_message(response, endpoint_id=1)

    assert websocket_module.ws_sync_button_state["full-update"] == "syncing"
    assert websocket_module._last_sync_activity == 10.0

    websocket_module.publish_backend_message(responses[-1], endpoint_id=1)

    assert websocket_module.ws_sync_button_state["full-update"] == "not-started"
    assert websocket_module.ws_sync_run_id["full-update"] is None
    assert websocket_module._last_sync_activity > 10.0


def test_legacy_latch_ignores_correlated_broadcast(websocket_module) -> None:
    _reset_state(websocket_module, active="devices", run_id=None)

    websocket_module.publish_backend_message(
        '{"object":"device","end":true,"run_id":"other_run_123"}',
        endpoint_id=1,
    )
    assert websocket_module.ws_sync_button_state["devices"] == "syncing"

    websocket_module.publish_backend_message(
        '{"object":"device","end":true}', endpoint_id=1
    )
    assert websocket_module.ws_sync_button_state["devices"] == "not-started"


def test_unrelated_frames_do_not_extend_expiry_or_release_the_successor(
    websocket_module, monkeypatch
) -> None:
    first_run = "first_run_123"
    second_run = "second_run_456"
    _reset_state(websocket_module, active="devices", run_id=first_run)
    websocket_module._last_sync_activity = 0.0
    monkeypatch.setattr(websocket_module.time, "monotonic", lambda: 500.0)

    websocket_module.publish_backend_message(
        '{"object":"device","end":false,"run_id":"other_run_789"}',
        endpoint_id=1,
    )
    assert websocket_module._last_sync_activity == 0.0

    monkeypatch.setattr(websocket_module.time, "monotonic", lambda: 601.0)
    with websocket_module.websocket_lock:
        websocket_module._expire_idle_sync_latch_locked()
    assert websocket_module.ws_sync_button_state["devices"] == "not-started"

    _reset_state(websocket_module, active="devices", run_id=second_run)
    websocket_module._last_sync_activity = 601.0
    monkeypatch.setattr(websocket_module.time, "monotonic", lambda: 602.0)
    websocket_module.publish_backend_message(
        json.dumps({"object": "device", "end": True, "run_id": first_run}),
        endpoint_id=1,
    )

    assert websocket_module.ws_sync_button_state["devices"] == "syncing"
    assert websocket_module.ws_sync_run_id["devices"] == second_run
    assert websocket_module._last_sync_activity == 601.0
