"""Bridge browser polling requests to the backend WebSocket message stream."""

from __future__ import annotations

import asyncio
import itertools
import json
import logging
import re
import secrets
import threading
import time
from collections import deque
from concurrent.futures import Future
from dataclasses import dataclass
from hashlib import sha256
from queue import Empty, Queue

import requests
import websockets
import websockets.exceptions
from asgiref.sync import sync_to_async
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views import View

from netbox_proxbox.models import FastAPIEndpoint
from netbox_proxbox.utils import get_backend_auth_headers, get_fastapi_url
from netbox_proxbox.views.proxbox_access import (
    permission_enqueue_proxbox_sync,
    permission_view_fastapi_endpoint,
)
from utilities.views import (
    ContentTypePermissionRequiredMixin,
    TokenConditionalLoginRequiredMixin,
)

logger = logging.getLogger(__name__)

_RECONNECT_DELAY_SEC = 5
_RECONNECT_MAX_DELAY_SEC = 60
_WS_CONNECTION_TIMEOUT = 10
_WS_RUNTIME_RECHECK_SEC = 2
_WS_CAPABILITY_CACHE_TTL_SEC = 30.0
_WS_CAPABILITY_TIMEOUT_SEC = 3
_WS_REJECTED_CAPABILITY_EXPIRY = float("inf")
_MAX_MESSAGE_QUEUE_SIZE = 1000
_MESSAGE_PAGE_SIZE = 20
_INVALID_COMMAND_MESSAGE = "Invalid sync command"
_RUN_MODE_OBJECT = "sync-run"
_TRUST_FAILURE_MESSAGE = "WebSocket endpoint trust changed before transmission."
# A running sync latch expires after this long without any backend message.
# Legacy proxbox-api sends no terminal when the VM stage of a full update is
# skipped, and any backend run may die with the connection. One stuck latch
# would otherwise block every sync kind until the worker restarts.
SYNC_LATCH_IDLE_TIMEOUT_SEC = 600.0
NEXT_CURSOR_HEADER = "X-Proxbox-Next-Cursor"

# Buffered backend messages as ``(sequence, message)`` pairs. Readers pass the
# last sequence they saw instead of draining the buffer, so concurrent users
# never consume each other's messages.
GLOBAL_WEBSOCKET_MESSAGES: deque[tuple[int, int, str]] = deque(maxlen=500)
_message_sequence = itertools.count(1)
_last_sequence = 0
_last_sync_activity = 0.0
# Cursors are only comparable within one process lifetime: each NetBox worker
# runs its own WebSocket client and buffer. The generation token lets a reader
# detect a cursor issued by another worker or before a restart.
BUFFER_GENERATION = secrets.token_hex(8)
_CURSOR_RE = re.compile(r"(?P<generation>[0-9a-f]{16})\.(?P<sequence>[0-9]{1,18})")
_RUN_ID_RE = re.compile(r"[A-Za-z0-9_-]{8,64}")
CURSOR_RESET_HEADER = "X-Proxbox-Cursor-Reset"
CURSOR_GAP_HEADER = "X-Proxbox-Cursor-Gap"
websocket_task: Future[None] | None = None
websocket_loop: asyncio.AbstractEventLoop | None = None
websocket_task_identity: tuple[int, str] | None = None
websocket_connection_identity: tuple[int, str, str] | None = None
websocket_lock = threading.Lock()
message_queue = Queue()
ws_sync_button_state = {
    "full-update": "not-started",
    "devices": "not-started",
    "virtual-machines": "not-started",
}
ws_sync_run_id: dict[str, str | None] = {
    "full-update": None,
    "devices": None,
    "virtual-machines": None,
}
_ws_capability_cache: dict[tuple[int, str, str], tuple[float, bool]] = {}
_END_OBJECT_TO_BUTTON: dict[str, str] = {
    "device": "devices",
    "virtual_machine": "virtual-machines",
    "full-update": "full-update",
}
SYNC_COMMANDS: dict[str, str] = {
    "full-update": "Full Update",
    "devices": "Sync Nodes",
    "virtual-machines": "Sync Virtual Machines",
}
_COMMAND_TO_KIND: dict[str, str] = {
    command: kind for kind, command in SYNC_COMMANDS.items()
}


@dataclass(frozen=True, slots=True)
class _WebSocketCredentials:
    """Ephemeral credentials loaded for one trusted WebSocket connection."""

    uri: str
    api_key: str
    identity: str
    http_url: str | None = None
    verify_ssl: bool = True
    auth_headers: dict[str, str] | None = None


@dataclass(frozen=True, slots=True)
class QueuedCommand:
    """A sync command bound to the worker that authorized it.

    The relay forwards a command only when the endpoint and trust identity
    match its own, so a command can never reach a different endpoint after the
    worker is stopped or replaced between authorization and dispatch.
    """

    endpoint_id: int
    identity: str
    command: str
    run_id: str | None = None
    connection_id: str | None = None


@dataclass(frozen=True, slots=True)
class _CommandDispatchContext:
    """Worker and connection generation checked before a POST queues work."""

    identity: tuple[int, str]
    connection: tuple[int, str, str] | None
    use_run_id: bool


class _WebSocketTrustLost(Exception):
    """Stop one connection after its endpoint trust identity changes."""


def _load_websocket_credentials(
    endpoint_id: int,
    expected_identity: str | None = None,
) -> _WebSocketCredentials | None:
    """Load a currently trusted server-side WebSocket configuration.

    The plaintext key is returned only to the active coroutine. Global task
    state stores a one-way identity, so rotation never leaves a reusable key in
    module-level configuration.
    """
    endpoint = (
        FastAPIEndpoint.objects.filter(
            pk=endpoint_id,
            enabled=True,
            use_websocket=True,
            server_side_websocket=True,
        )
        .order_by("pk")
        .first()
    )
    if endpoint is None:
        return None

    detail = get_fastapi_url(endpoint) or {}
    if not isinstance(detail, dict):
        return None
    uri = str(detail.get("server_websocket_url") or "").strip()
    http_url = str(detail.get("http_url") or "").strip() or None
    api_key = (endpoint.token or "").strip()
    target_fingerprint = str(endpoint.backend_key_target_fingerprint or "").strip()
    if not uri or not api_key or not target_fingerprint:
        return None

    identity = sha256(
        f"{endpoint.pk}\0{target_fingerprint}\0{api_key}".encode()
    ).hexdigest()
    if expected_identity is not None and identity != expected_identity:
        return None
    auth_headers = get_backend_auth_headers(endpoint)
    return _WebSocketCredentials(
        uri=uri,
        api_key=api_key,
        identity=identity,
        http_url=http_url,
        verify_ssl=bool(detail.get("verify_ssl", True)),
        auth_headers=auth_headers,
    )


async def _reload_credentials(
    endpoint_id: int, expected_identity: str
) -> _WebSocketCredentials | None:
    """Reload the endpoint trust state; ``None`` means configuration drift."""
    return await sync_to_async(
        _load_websocket_credentials,
        thread_sensitive=True,
    )(endpoint_id, expected_identity)


def _log_drift(endpoint_id: int) -> None:
    logger.info(
        "Stopping Proxbox plugin WebSocket for endpoint %s after configuration drift",
        endpoint_id,
    )


def _payload_supports_ws_run_id(payload: object) -> bool:
    """Return whether one backend metadata payload advertises capability v1."""
    if not isinstance(payload, dict):
        return False
    capabilities = payload.get("capabilities")
    if not isinstance(capabilities, dict):
        return False
    version = capabilities.get("ws_run_id")
    return type(version) is int and version == 1


def _capability_probe_targets(
    credentials: _WebSocketCredentials,
) -> tuple[tuple[str, dict[str, str]], ...]:
    """Return existing metadata/health endpoints and their current auth policy."""
    base_url = (credentials.http_url or "").rstrip("/")
    if not base_url:
        return ()
    auth_headers = credentials.auth_headers or {}
    return (
        (base_url, {}),
        (f"{base_url}/health", auth_headers),
        (f"{base_url}/version", auth_headers),
    )


def _probe_backend_ws_run_id(endpoint_id: int, expected_identity: str) -> bool:
    """Read the additive capability without risking a JSON frame on old backends."""
    credentials = _load_websocket_credentials(endpoint_id, expected_identity)
    if credentials is None:
        return False
    deadline = time.monotonic() + _WS_CAPABILITY_TIMEOUT_SEC
    for url, headers in _capability_probe_targets(credentials):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            request_timeout = max(0.001, remaining)
            response = requests.get(
                url,
                headers=headers,
                verify=credentials.verify_ssl,
                timeout=request_timeout,
                allow_redirects=False,
            )
            if not 200 <= response.status_code < 300:
                continue
            if _payload_supports_ws_run_id(response.json()):
                return True
        except Exception as exc:  # noqa: BLE001 - capability doubt is legacy-safe
            logger.debug(
                "WebSocket run-id capability probe failed for endpoint %s (%s)",
                endpoint_id,
                type(exc).__name__,
            )
    return False


def _backend_supports_ws_run_id(
    endpoint_id: int,
    expected_identity: str,
    connection_id: str,
    *,
    refresh: bool = False,
) -> bool:
    """Return a short-lived capability decision for one WebSocket connection."""
    key = (endpoint_id, expected_identity, connection_id)
    now = time.monotonic()
    with websocket_lock:
        if websocket_connection_identity != key:
            return False
        cached = _ws_capability_cache.get(key)
        if cached is not None and cached[0] == _WS_REJECTED_CAPABILITY_EXPIRY:
            return False
        if not refresh and cached is not None and cached[0] > now:
            return cached[1]

    supported = _probe_backend_ws_run_id(endpoint_id, expected_identity)
    with websocket_lock:
        cached = _ws_capability_cache.get(key)
        if cached is not None and cached[0] == _WS_REJECTED_CAPABILITY_EXPIRY:
            return False
        if websocket_connection_identity != key:
            return False
        stale = [
            cache_key
            for cache_key, cache_value in _ws_capability_cache.items()
            if cache_value[0] <= now
        ]
        for cache_key in stale:
            _ws_capability_cache.pop(cache_key, None)
        _ws_capability_cache[key] = (
            time.monotonic() + _WS_CAPABILITY_CACHE_TTL_SEC,
            supported,
        )
    return supported


def _invalidate_positive_capability_locked(
    endpoint_id: int, expected_identity: str
) -> None:
    """Drop positive decisions whenever a matching connection changes."""
    stale = [
        key
        for key, (_expires, supported) in _ws_capability_cache.items()
        if key[:2] == (endpoint_id, expected_identity) and supported
    ]
    for key in stale:
        _ws_capability_cache.pop(key, None)


def _open_connection_session(endpoint_id: int, expected_identity: str) -> str:
    """Register a new authenticated WebSocket connection generation."""
    global websocket_connection_identity
    connection_id = secrets.token_hex(16)
    with websocket_lock:
        _invalidate_positive_capability_locked(endpoint_id, expected_identity)
        websocket_connection_identity = (
            endpoint_id,
            expected_identity,
            connection_id,
        )
    return connection_id


def _close_connection_session(
    endpoint_id: int, expected_identity: str, connection_id: str
) -> None:
    """Forget one exact WebSocket connection and its positive capability."""
    global websocket_connection_identity
    with websocket_lock:
        _invalidate_positive_capability_locked(endpoint_id, expected_identity)
        _ws_capability_cache.pop(
            (endpoint_id, expected_identity, connection_id),
            None,
        )
        if websocket_connection_identity == (
            endpoint_id,
            expected_identity,
            connection_id,
        ):
            websocket_connection_identity = None


def _mark_connection_capability_negative(
    endpoint_id: int, expected_identity: str, connection_id: str
) -> None:
    """Remember an envelope rejection for the current connection generation."""
    with websocket_lock:
        _ws_capability_cache[(endpoint_id, expected_identity, connection_id)] = (
            _WS_REJECTED_CAPABILITY_EXPIRY,
            False,
        )


def _valid_run_id(value: object) -> str | None:
    """Return one protocol-valid run id without hashing untrusted JSON values."""
    if not isinstance(value, str) or _RUN_ID_RE.fullmatch(value) is None:
        return None
    return value


def _payload_run_id(
    payload: dict[str, object] | None,
) -> tuple[bool, str | None]:
    """Return whether a run id field exists and its validated string value."""
    if payload is None or "run_id" not in payload:
        return False, None
    return True, _valid_run_id(payload.get("run_id"))


def _protocol_payload_is_malformed(payload: dict[str, object] | None) -> bool:
    """Reject malformed correlation fields before state or activity handling."""
    run_id_present, run_id = _payload_run_id(payload)
    if run_id_present and run_id is None:
        return True
    if (
        payload is not None
        and payload.get("object") == "full-update"
        and payload.get("end") is True
    ):
        status = payload.get("status")
        return not isinstance(status, str) or status not in ("completed", "failed")
    return False


def _message_payload(response: object) -> dict[str, object] | None:
    """Parse one backend message mapping without trusting its wire shape."""
    if isinstance(response, dict):
        return response
    if response is None:
        return None
    try:
        payload = json.loads(response)
    except (TypeError, json.JSONDecodeError):
        logger.debug("Received a non-JSON backend WebSocket message")
        return None
    return payload if isinstance(payload, dict) else None


def _terminal_payload(response: object) -> dict[str, object] | None:
    """Return a terminal mapping, or ``None`` for progress and invalid JSON."""
    payload = _message_payload(response)
    if payload is None or payload.get("end") is not True:
        return None
    return payload


def _candidate_buttons(payload: dict[str, object]) -> tuple[str, ...]:
    """Map a terminal object to the legacy buttons it could release."""
    button = _END_OBJECT_TO_BUTTON.get(str(payload.get("object") or ""))
    if button is None:
        return ()
    if button == "virtual-machines":
        return (button, "full-update")
    return (button,)


def _run_matches_button(payload: dict[str, object], button: str) -> bool:
    """Require exact run identity when either the message or run is correlated."""
    expected = ws_sync_run_id.get(button)
    run_id_present, observed = _payload_run_id(payload)
    if run_id_present and observed is None:
        logger.debug("Ignoring WebSocket terminal with a malformed run_id")
        return False
    if expected is None and not run_id_present:
        return True
    if expected is None or observed != expected:
        return False
    if button != "full-update":
        return True
    if payload.get("object") != "full-update":
        logger.debug(
            "Ignoring per-stage terminal for correlated full-update run_id=%s",
            expected,
        )
        return False
    status = payload.get("status")
    if not isinstance(status, str) or status not in ("completed", "failed"):
        logger.debug("Ignoring correlated full-update terminal with invalid status")
        return False
    return True


def _buttons_released_by(response: object) -> tuple[str, ...]:
    """Return the sync buttons a backend terminal message releases.

    Legacy runs preserve the VM-terminal full-update behavior. Correlated runs
    require an exact run id, and correlated full updates require their aggregate
    terminal instead of a per-stage terminal.
    """
    payload = _terminal_payload(response)
    if payload is None:
        return ()
    return tuple(
        button
        for button in _candidate_buttons(payload)
        if ws_sync_button_state.get(button) == "syncing"
        and _run_matches_button(payload, button)
    )


def _log_ignored_correlated_message(payload: dict[str, object] | None) -> None:
    """Record a frame that cannot belong to the active correlated run."""
    expected = _active_correlated_run_ids()
    if not expected or payload is None:
        return
    run_id_present, observed = _payload_run_id(payload)
    if run_id_present and observed is None:
        logger.debug("Ignoring WebSocket message with a malformed run_id")
        return
    if observed is not None and observed in expected:
        return
    logger.debug(
        "Not attributing WebSocket message to correlated run(s) %s: received run_id=%r",
        sorted(expected),
        observed,
    )


def _active_correlated_run_ids() -> set[str]:
    """Return run ids whose sync latches currently require correlation."""
    return {
        run_id
        for kind, run_id in ws_sync_run_id.items()
        if ws_sync_button_state.get(kind) == "syncing" and run_id is not None
    }


def _message_marks_sync_activity(payload: dict[str, object] | None) -> bool:
    """Ignore unrelated frames when refreshing a correlated run's idle latch."""
    expected = _active_correlated_run_ids()
    if not expected:
        return True
    _present, observed = _payload_run_id(payload)
    return observed is not None and observed in expected


def publish_backend_message(message: str, *, endpoint_id: int) -> int:
    """Release finished sync buttons and buffer ``message`` in one critical section.

    Publishing the terminal and releasing its button atomically means a POST
    can never observe a released button whose terminal is not yet buffered (or
    the reverse) and hand a new run a cursor that already contains the previous
    run's terminal.
    """
    with websocket_lock:
        payload = _message_payload(message)
        malformed = _protocol_payload_is_malformed(payload)
        if malformed:
            logger.debug("Ignoring WebSocket message with malformed protocol fields")
        _log_ignored_correlated_message(payload)
        mark_activity = not malformed and _message_marks_sync_activity(payload)
        released = () if malformed else _buttons_released_by(payload)
        for button in released:
            ws_sync_button_state[button] = "not-started"
            ws_sync_run_id[button] = None
        return _append_message_locked(
            message,
            endpoint_id,
            mark_sync_activity=mark_activity,
        )


def _is_invalid_command_frame(
    message: object,
    payload: dict[str, object] | None,
    pending_envelope: QueuedCommand,
) -> bool:
    """Recognize an invalid-command response attributable to one envelope."""
    if message == _INVALID_COMMAND_MESSAGE:
        return True
    if payload is None or payload.get("message") != _INVALID_COMMAND_MESSAGE:
        return False
    run_id_present, run_id = _payload_run_id(payload)
    return run_id_present and run_id == pending_envelope.run_id


def _active_pending_envelope(
    pending_envelope: QueuedCommand | None,
) -> QueuedCommand | None:
    """Retain a pending envelope only while its exact run still owns the latch."""
    if pending_envelope is None:
        return None
    kind = _COMMAND_TO_KIND.get(pending_envelope.command)
    with websocket_lock:
        active = (
            kind is not None
            and ws_sync_button_state.get(kind) == "syncing"
            and ws_sync_run_id.get(kind) == pending_envelope.run_id
        )
    if active:
        return pending_envelope
    logger.debug(
        "Retiring inactive pending WebSocket envelope run_id=%s",
        pending_envelope.run_id,
    )
    return None


def _fail_active_syncs_for_trust_loss(endpoint_id: int) -> None:
    """Release active latches and publish a poll-visible trust failure."""
    with websocket_lock:
        for kind, state in ws_sync_button_state.items():
            if state != "syncing":
                continue
            run_id = ws_sync_run_id.get(kind)
            payload: dict[str, object] = {
                "object": _RUN_MODE_OBJECT,
                "end": True,
                "status": "failed",
                "kind": kind,
                "error": _TRUST_FAILURE_MESSAGE,
            }
            if run_id is not None:
                payload["run_id"] = run_id
            ws_sync_button_state[kind] = "not-started"
            ws_sync_run_id[kind] = None
            _append_message_locked(
                json.dumps(payload, separators=(",", ":")),
                endpoint_id,
            )


async def _require_transmission_trust(
    endpoint_id: int,
    expected_identity: str,
) -> None:
    """Fail closed unless the original endpoint trust identity still exists."""
    if await _reload_credentials(endpoint_id, expected_identity) is not None:
        return
    _fail_active_syncs_for_trust_loss(endpoint_id)
    _log_drift(endpoint_id)
    raise _WebSocketTrustLost


def _downgrade_queued_run_locked(queued: QueuedCommand, *, endpoint_id: int) -> bool:
    """Convert one still-active correlated command to legacy polling metadata."""
    kind = _COMMAND_TO_KIND.get(queued.command)
    if (
        kind is None
        or queued.run_id is None
        or ws_sync_button_state.get(kind) != "syncing"
        or ws_sync_run_id.get(kind) != queued.run_id
    ):
        return False
    ws_sync_run_id[kind] = None
    control = json.dumps(
        {
            "object": _RUN_MODE_OBJECT,
            "run_id": queued.run_id,
            "correlated": False,
        },
        separators=(",", ":"),
    )
    _append_message_locked(control, endpoint_id)
    return True


def _downgrade_queued_run(queued: QueuedCommand, *, endpoint_id: int) -> bool:
    """Thread-safe wrapper for publishing a correlated-to-legacy transition."""
    with websocket_lock:
        return _downgrade_queued_run_locked(queued, endpoint_id=endpoint_id)


async def _dispatch_queued_command(
    queued: object,
    endpoint_id: int,
    expected_identity: str,
    connection_id: str,
) -> tuple[str | None, QueuedCommand | None]:
    """Format one command using a fresh decision for the current connection."""
    if not isinstance(queued, QueuedCommand):
        return (
            _command_for_worker(
                queued,
                endpoint_id,
                expected_identity,
                connection_id=connection_id,
                supports_run_id=False,
            ),
            None,
        )
    bound = queued.endpoint_id == endpoint_id and queued.identity == expected_identity
    supports_run_id = False
    if bound and queued.run_id is not None:
        supports_run_id = await sync_to_async(
            _backend_supports_ws_run_id,
            thread_sensitive=True,
        )(
            endpoint_id,
            expected_identity,
            connection_id,
            refresh=True,
        )
    await _require_transmission_trust(endpoint_id, expected_identity)
    frame = _command_for_worker(
        queued,
        endpoint_id,
        expected_identity,
        connection_id=connection_id,
        supports_run_id=supports_run_id,
    )
    pending = queued if frame is not None and supports_run_id else None
    return frame, pending


async def _handle_connected_response(
    websocket: object,
    response: object,
    pending_envelope: QueuedCommand | None,
    endpoint_id: int,
    expected_identity: str,
    connection_id: str,
) -> QueuedCommand | None:
    """Handle envelope rejection or publish one ordinary backend frame."""
    pending_envelope = _active_pending_envelope(pending_envelope)
    payload = _message_payload(response)
    if pending_envelope is not None and _is_invalid_command_frame(
        response,
        payload,
        pending_envelope,
    ):
        await _require_transmission_trust(endpoint_id, expected_identity)
        _mark_connection_capability_negative(
            endpoint_id,
            expected_identity,
            connection_id,
        )
        if _downgrade_queued_run(pending_envelope, endpoint_id=endpoint_id):
            await websocket.send(pending_envelope.command)
        return None
    if pending_envelope is not None:
        _present, response_run_id = _payload_run_id(payload)
        if response_run_id == pending_envelope.run_id:
            pending_envelope = None
    publish_backend_message(response, endpoint_id=endpoint_id)
    return pending_envelope


async def _run_connected_session(
    websocket: object,
    endpoint_id: int,
    expected_identity: str,
    connection_id: str,
) -> None:
    """Relay queued commands and record backend messages until trust drifts."""
    loop = asyncio.get_running_loop()
    last_runtime_check = loop.time()
    pending_envelope: QueuedCommand | None = None
    while True:
        if loop.time() - last_runtime_check >= _WS_RUNTIME_RECHECK_SEC:
            await _require_transmission_trust(endpoint_id, expected_identity)
            last_runtime_check = loop.time()

        pending_envelope = _active_pending_envelope(pending_envelope)
        if pending_envelope is None and not message_queue.empty():
            # Recheck immediately before forwarding a queued command; an active
            # stream may otherwise prevent recv timeouts.
            await _require_transmission_trust(endpoint_id, expected_identity)
            last_runtime_check = loop.time()
            try:
                # Never block the event loop: a concurrent discard may have
                # drained the queue since the emptiness check.
                queued = message_queue.get_nowait()
            except Empty:
                queued = None
            command, pending_envelope = await _dispatch_queued_command(
                queued,
                endpoint_id,
                expected_identity,
                connection_id,
            )
            if command is not None:
                await websocket.send(command)

        next_check_in = max(
            _WS_RUNTIME_RECHECK_SEC - (loop.time() - last_runtime_check),
            0.01,
        )
        try:
            response = await asyncio.wait_for(websocket.recv(), timeout=next_check_in)
        except TimeoutError:
            await _require_transmission_trust(endpoint_id, expected_identity)
            last_runtime_check = loop.time()
            continue
        pending_envelope = await _handle_connected_response(
            websocket,
            response,
            pending_envelope,
            endpoint_id,
            expected_identity,
            connection_id,
        )


async def _connect_and_relay(
    credentials: _WebSocketCredentials,
    endpoint_id: int,
    expected_identity: str,
    attempt: dict[str, bool],
) -> None:
    """Open one trusted connection and relay until trust drifts.

    Returning normally means the worker must stop. ``attempt["connected"]`` is
    set once the key was sent, so a later disconnect resets the back-off.
    """
    connector = websockets.connect(
        credentials.uri,
        open_timeout=_WS_CONNECTION_TIMEOUT,
        proxy=None,
    )
    async with connector as websocket:
        if str(connector.uri) != credentials.uri:
            logger.warning(
                "Refusing redirected backend WebSocket for endpoint %s",
                endpoint_id,
            )
            return
        # The handshake can take several seconds. Reload immediately before
        # sending the key so a save/disable during connect cannot emit the
        # stale credential once.
        current = await _reload_credentials(endpoint_id, expected_identity)
        if current is None:
            return
        logger.info("Proxbox plugin WebSocket connected for endpoint %s", endpoint_id)
        await websocket.send(json.dumps({"api_key": current.api_key}))
        attempt["connected"] = True
        connection_id = _open_connection_session(endpoint_id, expected_identity)
        try:
            try:
                await _run_connected_session(
                    websocket,
                    endpoint_id,
                    expected_identity,
                    connection_id,
                )
            except _WebSocketTrustLost:
                pass
        finally:
            _close_connection_session(
                endpoint_id,
                expected_identity,
                connection_id,
            )


async def websocket_client(endpoint_id: int, expected_identity: str) -> None:
    """Maintain a WebSocket only while the endpoint remains exactly trusted."""
    reconnect_delay = _RECONNECT_DELAY_SEC
    while True:
        credentials = await _reload_credentials(endpoint_id, expected_identity)
        if credentials is None:
            _log_drift(endpoint_id)
            return
        attempt = {"connected": False}
        try:
            await _connect_and_relay(
                credentials, endpoint_id, expected_identity, attempt
            )
            return
        except asyncio.CancelledError:
            raise
        except websockets.exceptions.ConnectionClosed as exc:
            logger.warning(
                "WebSocket closed (code=%s); reconnecting in %ss",
                getattr(exc, "code", None),
                reconnect_delay,
            )
        except websockets.exceptions.InvalidStatus as exc:
            response = getattr(exc, "response", None)
            status_code = getattr(response, "status_code", None)
            if status_code in (401, 403):
                logger.error(
                    "WebSocket handshake refused (HTTP %s) for %s; stopping retries.",
                    status_code,
                    credentials.uri,
                )
                return
            logger.warning(
                "WebSocket handshake failed (HTTP %s) for %s; retrying in %ss",
                status_code,
                credentials.uri,
                reconnect_delay,
            )
        except OSError as exc:
            logger.warning(
                "WebSocket connect error (%s) for endpoint %s; retrying in %ss",
                type(exc).__name__,
                endpoint_id,
                reconnect_delay,
            )
        except (KeyboardInterrupt, SystemExit, GeneratorExit):
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Unexpected WebSocket error (%s) for endpoint %s; retrying in %ss",
                type(exc).__name__,
                endpoint_id,
                reconnect_delay,
            )
        if attempt["connected"]:
            reconnect_delay = _RECONNECT_DELAY_SEC
        await asyncio.sleep(reconnect_delay)
        reconnect_delay = min(reconnect_delay * 2, _RECONNECT_MAX_DELAY_SEC)


def start_websocket(endpoint_id: int) -> bool:
    """Start or replace the worker for one exact trusted endpoint state."""
    global websocket_task, websocket_loop, websocket_task_identity
    credentials = _load_websocket_credentials(endpoint_id)
    if credentials is None:
        stop_websocket(endpoint_id)
        return False
    identity = (endpoint_id, credentials.identity)

    with websocket_lock:
        if (
            websocket_task is not None
            and not websocket_task.done()
            and websocket_task_identity == identity
        ):
            return True
        if websocket_task is not None and not websocket_task.done():
            websocket_task.cancel()
        if websocket_task_identity is not None:
            # Replacing a worker: queued commands belonged to the old one.
            _discard_pending_commands_locked()

        if websocket_loop is None or websocket_loop.is_closed():
            websocket_loop = asyncio.new_event_loop()

            def run_loop() -> None:
                loop = websocket_loop
                if loop is None:  # pragma: no cover - guarded before thread start
                    return
                asyncio.set_event_loop(loop)
                loop.run_forever()

            thread = threading.Thread(target=run_loop, daemon=True)
            thread.start()
        websocket_task_identity = identity
        websocket_task = asyncio.run_coroutine_threadsafe(
            websocket_client(endpoint_id, credentials.identity), websocket_loop
        )
    return True


def stop_websocket(endpoint_id: int | None = None) -> bool:
    """Cancel the worker when its endpoint is saved, disabled, or rotated."""
    global websocket_task, websocket_task_identity, websocket_connection_identity
    with websocket_lock:
        if websocket_task_identity is None:
            return False
        if endpoint_id is not None and websocket_task_identity[0] != endpoint_id:
            return False
        identity = websocket_task_identity
        task = websocket_task
        websocket_task = None
        websocket_task_identity = None
        if task is not None and not task.done():
            task.cancel()
        connection = websocket_connection_identity
        if connection is not None and connection[0] == identity[0]:
            _invalidate_positive_capability_locked(connection[0], connection[1])
            _ws_capability_cache.pop(connection, None)
            websocket_connection_identity = None
        _discard_pending_commands_locked()
        return True


@dataclass(frozen=True, slots=True)
class MessagePage:
    """One cursor read of buffered backend messages for a single endpoint."""

    messages: list[str]
    next_sequence: int
    gap: bool


def _append_message_locked(
    message: str,
    endpoint_id: int,
    *,
    mark_sync_activity: bool = True,
) -> int:
    """Append one message; the caller must hold ``websocket_lock``."""
    global _last_sequence, _last_sync_activity
    if mark_sync_activity:
        _last_sync_activity = time.monotonic()
    _last_sequence = next(_message_sequence)
    GLOBAL_WEBSOCKET_MESSAGES.append((_last_sequence, endpoint_id, message))
    return _last_sequence


def record_websocket_message(message: str, *, endpoint_id: int) -> int:
    """Append one backend message for ``endpoint_id`` and return its sequence."""
    with websocket_lock:
        return _append_message_locked(message, endpoint_id)


def _mark_sync_activity_locked() -> None:
    """Record sync activity now; the caller must hold ``websocket_lock``."""
    global _last_sync_activity
    _last_sync_activity = time.monotonic()


def _expire_idle_sync_latch_locked() -> None:
    """Release running latches after a long backend silence (caller holds lock)."""
    if not any(state != "not-started" for state in ws_sync_button_state.values()):
        return
    if time.monotonic() - _last_sync_activity < SYNC_LATCH_IDLE_TIMEOUT_SEC:
        return
    logger.warning(
        "Releasing Proxbox WebSocket sync latch after %ss without backend activity",
        int(SYNC_LATCH_IDLE_TIMEOUT_SEC),
    )
    for kind in ws_sync_button_state:
        ws_sync_button_state[kind] = "not-started"
        ws_sync_run_id[kind] = None


def _release_command_locked(queued: object) -> None:
    """Release the button of a command that will never be sent."""
    if isinstance(queued, QueuedCommand):
        kind = _COMMAND_TO_KIND.get(queued.command)
        if kind is not None and ws_sync_run_id.get(kind) == queued.run_id:
            ws_sync_button_state[kind] = "not-started"
            ws_sync_run_id[kind] = None


def _command_for_worker(
    queued: object,
    endpoint_id: int,
    expected_identity: str,
    *,
    connection_id: str,
    supports_run_id: bool,
) -> str | None:
    """Format a bound command for the capability of its dispatch connection."""
    if queued is None:
        return None
    if (
        isinstance(queued, QueuedCommand)
        and queued.endpoint_id == endpoint_id
        and queued.identity == expected_identity
    ):
        if queued.run_id is None:
            return queued.command
        if supports_run_id:
            if queued.connection_id != connection_id:
                logger.debug(
                    "Dispatching correlated run_id=%s on a replacement connection",
                    queued.run_id,
                )
            return json.dumps(
                {"command": queued.command, "run_id": queued.run_id},
                separators=(",", ":"),
            )
        _downgrade_queued_run(queued, endpoint_id=endpoint_id)
        return queued.command
    logger.warning(
        "Dropping a queued WebSocket command not bound to endpoint %s", endpoint_id
    )
    with websocket_lock:
        _release_command_locked(queued)
    return None


def _discard_pending_commands_locked() -> None:
    """Drop queued commands and release their buttons; caller holds the lock.

    Commands are not bound to an endpoint, so a command queued for one worker
    must never be delivered by a replacement worker for another endpoint.
    """
    while True:
        try:
            dropped = message_queue.get_nowait()
        except Empty:
            break
        # Only a command that was never sent releases its button; a run the
        # backend already received keeps its button latched (fail closed).
        _release_command_locked(dropped)


def format_message_cursor(sequence: int) -> str:
    """Bind a sequence to this process's buffer generation."""
    return f"{BUFFER_GENERATION}.{int(sequence)}"


def parse_message_cursor(raw: object) -> tuple[int | None, bool]:
    """Parse ``after`` into ``(sequence, reset)``; raise ``ValueError`` if malformed.

    A well-formed cursor issued by another worker process or before a restart
    has a different generation. It cannot be compared with this buffer, so it
    is discarded and ``reset`` is ``True``.
    """
    if raw is None or raw == "":
        return None, False
    match = _CURSOR_RE.fullmatch(str(raw).strip())
    if match is None:
        raise ValueError("malformed cursor")
    if match.group("generation") != BUFFER_GENERATION:
        return None, True
    return int(match.group("sequence")), False


def read_messages_after(
    endpoint_id: int, after: int | None, limit: int = _MESSAGE_PAGE_SIZE
) -> MessagePage:
    """Return ``endpoint_id`` messages newer than ``after`` without removing them.

    Without a cursor the newest ``limit`` messages are returned. ``gap`` is set
    when older messages after the cursor were evicted from the bounded buffer.
    """
    with websocket_lock:
        entries = list(GLOBAL_WEBSOCKET_MESSAGES)
        last_sequence = _last_sequence
    own = [(seq, msg) for seq, owner, msg in entries if owner == endpoint_id]
    if after is None:
        selected = own[-limit:] if limit > 0 else []
    else:
        selected = [entry for entry in own if entry[0] > after][:limit]
    oldest = entries[0][0] if entries else last_sequence + 1
    gap = after is not None and after < oldest - 1
    if selected:
        next_sequence = selected[-1][0]
    else:
        next_sequence = last_sequence if after is None else max(after, 0)
    return MessagePage([msg for _seq, msg in selected], next_sequence, gap)


def send_message(
    message: str,
    *,
    endpoint_id: int,
    identity: str,
    use_run_id: bool = False,
    connection_id: str | None = None,
) -> str | None:
    """Enqueue a command and return its run id when correlation is supported."""
    if message_queue.qsize() >= _MAX_MESSAGE_QUEUE_SIZE:
        logger.warning(
            "Message queue full (%d), dropping message", _MAX_MESSAGE_QUEUE_SIZE
        )
        return None
    run_id = secrets.token_hex(16) if use_run_id else None
    message_queue.put(
        QueuedCommand(
            endpoint_id=endpoint_id,
            identity=identity,
            command=message,
            run_id=run_id,
            connection_id=connection_id,
        )
    )
    return run_id


def _command_dispatch_context(
    endpoint_pk: int,
) -> tuple[_CommandDispatchContext | None, HttpResponse | None]:
    """Probe capability for the currently authenticated connection generation."""
    with websocket_lock:
        identity = websocket_task_identity
        if identity is None or identity[0] != endpoint_pk:
            return None, JsonResponse(
                {"error": "The WebSocket worker changed; retry the request."},
                status=409,
            )
        connection = websocket_connection_identity
        if connection is not None and connection[:2] != identity:
            connection = None
    use_run_id = connection is not None and _backend_supports_ws_run_id(
        endpoint_pk,
        identity[1],
        connection[2],
    )
    return _CommandDispatchContext(identity, connection, use_run_id), None


def _queue_sync_command(
    message: str,
    command: str,
    context: _CommandDispatchContext,
) -> HttpResponse:
    """Atomically latch and enqueue one command for a validated context."""
    with websocket_lock:
        if websocket_task_identity != context.identity:
            return JsonResponse(
                {"error": "The WebSocket worker changed; retry the request."},
                status=409,
            )
        if (
            context.connection is not None
            and websocket_connection_identity != context.connection
        ):
            return JsonResponse(
                {"error": "The WebSocket connection changed; retry the request."},
                status=409,
            )
        cursor = format_message_cursor(_last_sequence)
        _expire_idle_sync_latch_locked()
        queued = all(state == "not-started" for state in ws_sync_button_state.values())
        run_id = None
        if queued:
            ws_sync_button_state[message] = "syncing"
            _mark_sync_activity_locked()
            run_id = send_message(
                command,
                endpoint_id=context.identity[0],
                identity=context.identity[1],
                use_run_id=context.use_run_id,
                connection_id=(
                    context.connection[2] if context.connection is not None else None
                ),
            )
            ws_sync_run_id[message] = run_id
        elif ws_sync_button_state.get(message) == "syncing":
            run_id = ws_sync_run_id.get(message)
    payload = {"kind": message, "queued": queued, "cursor": cursor}
    if run_id is not None:
        payload["run_id"] = run_id
    return JsonResponse(payload, status=202 if queued else 409)


class WebSocketView(
    TokenConditionalLoginRequiredMixin,
    ContentTypePermissionRequiredMixin,
    View,
):
    """Read buffered backend WebSocket messages (GET) or start a sync (POST).

    GET is read-only: it never sends a command upstream and never removes
    messages from the shared buffer. Starting a sync is a state change, so it
    requires POST (CSRF-protected by Django's middleware) and the same
    ``core.add_job`` permission as the other Proxbox sync entry points.
    """

    template_name = "netbox_proxbox/websocket_page.html"
    http_method_names = ["get", "post"]

    def get_required_permission(self) -> str:
        """Require FastAPI endpoint view permission to read backend stream state."""
        return permission_view_fastapi_endpoint()

    @staticmethod
    def _select_endpoint(request: HttpRequest) -> FastAPIEndpoint | None:
        """Return the shared worker's endpoint if the caller may view it.

        The process runs one WebSocket worker, always for the first eligible
        endpoint. Selecting per user would let one user's poll cancel and
        replace the worker another user depends on, so the selection stays
        deterministic and the caller must be permitted to view that exact
        endpoint under NetBox object permissions.
        """
        endpoint = (
            FastAPIEndpoint.objects.filter(
                enabled=True,
                use_websocket=True,
                server_side_websocket=True,
            )
            .order_by("pk")
            .first()
        )
        if endpoint is None:
            return None
        permitted = (
            FastAPIEndpoint.objects.restrict(request.user, "view")
            .filter(pk=endpoint.pk)
            .exists()
        )
        return endpoint if permitted else None

    def _ensure_worker(
        self, request: HttpRequest
    ) -> tuple[int | None, HttpResponse | None]:
        """Start the worker for a permitted endpoint; return ``(pk, error)``."""
        fastapi_object = self._select_endpoint(request)
        if fastapi_object is None or not bool(
            getattr(fastapi_object, "enabled", False)
        ):
            return None, HttpResponse(
                "Enabled FastAPIEndpoint object not found", status=404
            )

        fastapi_detail = get_fastapi_url(fastapi_object) or {}
        if not isinstance(fastapi_detail, dict):
            fastapi_detail = {}
        if not fastapi_detail.get("server_websocket_url"):
            return None, HttpResponse("WebSocket URL not found", status=404)

        endpoint_pk = int(fastapi_object.pk)
        if not start_websocket(endpoint_pk):
            return None, HttpResponse(
                "Trusted WebSocket configuration not found", status=404
            )
        return endpoint_pk, None

    def get(self, request: HttpRequest, message: str) -> HttpResponse:
        """Return buffered messages newer than the ``after`` cursor.

        The ``message`` path segment is accepted for URL compatibility only;
        a GET never starts a sync.
        """
        del message
        try:
            cursor, reset = parse_message_cursor(request.GET.get("after"))
        except ValueError:
            return JsonResponse({"error": "Invalid cursor."}, status=400)

        endpoint_pk, error = self._ensure_worker(request)
        if error is not None:
            return error

        page = read_messages_after(endpoint_pk, cursor)
        if request.GET.get("json_response", "false").lower() == "true":
            response = JsonResponse(page.messages, safe=False)
        else:
            response = render(request, self.template_name, {"messages": page.messages})
        response[NEXT_CURSOR_HEADER] = format_message_cursor(page.next_sequence)
        if reset:
            response[CURSOR_RESET_HEADER] = "1"
        if page.gap:
            response[CURSOR_GAP_HEADER] = "1"
        return response

    def post(self, request: HttpRequest, message: str) -> HttpResponse:
        """Queue one sync command for the backend WebSocket."""
        command = SYNC_COMMANDS.get(message)
        if command is None:
            return JsonResponse({"error": "Unknown sync kind."}, status=404)
        if not request.user.has_perm(permission_enqueue_proxbox_sync()):
            return JsonResponse(
                {"error": "You do not have permission to start a Proxbox sync."},
                status=403,
            )

        endpoint_pk, error = self._ensure_worker(request)
        if error is not None:
            return error
        context, error = _command_dispatch_context(endpoint_pk)
        if error is not None:
            return error
        return _queue_sync_command(message, command, context)
