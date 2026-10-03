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

import websockets
import websockets.exceptions
from asgiref.sync import sync_to_async
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views import View

from netbox_proxbox.models import FastAPIEndpoint
from netbox_proxbox.utils import get_fastapi_url
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
_MAX_MESSAGE_QUEUE_SIZE = 1000
_MESSAGE_PAGE_SIZE = 20
# A running sync latch expires after this long without any backend message.
# proxbox-api sends no terminal when the VM stage of a full update is skipped
# or a run dies with the connection, and one stuck latch would otherwise block
# every sync kind until the worker restarts.
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
CURSOR_RESET_HEADER = "X-Proxbox-Cursor-Reset"
CURSOR_GAP_HEADER = "X-Proxbox-Cursor-Gap"
websocket_task: Future[None] | None = None
websocket_loop: asyncio.AbstractEventLoop | None = None
websocket_task_identity: tuple[int, str] | None = None
websocket_lock = threading.Lock()
message_queue = Queue()
ws_sync_button_state = {
    "full-update": "not-started",
    "devices": "not-started",
    "virtual-machines": "not-started",
}
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
    api_key = (endpoint.token or "").strip()
    target_fingerprint = str(endpoint.backend_key_target_fingerprint or "").strip()
    if not uri or not api_key or not target_fingerprint:
        return None

    identity = sha256(
        f"{endpoint.pk}\0{target_fingerprint}\0{api_key}".encode()
    ).hexdigest()
    if expected_identity is not None and identity != expected_identity:
        return None
    return _WebSocketCredentials(uri=uri, api_key=api_key, identity=identity)


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


def _buttons_released_by(response: object) -> tuple[str, ...]:
    """Return the sync buttons a backend terminal message releases.

    proxbox-api has no aggregate full-update terminal: a full update runs the
    device stage and then the VM stage, so the VM-stage terminal also releases
    the full-update button. The device-stage terminal deliberately does not:
    releasing it there would let a second full update start while the first is
    still syncing virtual machines.
    """
    try:
        response_dict = json.loads(response)
    except (TypeError, json.JSONDecodeError):
        logger.debug("Received a non-JSON backend WebSocket message")
        return ()
    if not isinstance(response_dict, dict) or response_dict.get("end") is not True:
        return ()
    button = _END_OBJECT_TO_BUTTON.get(response_dict.get("object"))
    if button is None:
        return ()
    if button == "virtual-machines":
        # Only one sync runs at a time (see WebSocketView.post), so a VM-stage
        # terminal ends either a VM sync or the full update that owns it.
        return (button, "full-update")
    return (button,)


def publish_backend_message(message: str, *, endpoint_id: int) -> int:
    """Release finished sync buttons and buffer ``message`` in one critical section.

    Publishing the terminal and releasing its button atomically means a POST
    can never observe a released button whose terminal is not yet buffered (or
    the reverse) and hand a new run a cursor that already contains the previous
    run's terminal.
    """
    released = _buttons_released_by(message)
    with websocket_lock:
        for button in released:
            ws_sync_button_state[button] = "not-started"
        return _append_message_locked(message, endpoint_id)


async def _run_connected_session(
    websocket: object, endpoint_id: int, expected_identity: str
) -> None:
    """Relay queued commands and record backend messages until trust drifts."""
    loop = asyncio.get_running_loop()
    last_runtime_check = loop.time()
    while True:
        if loop.time() - last_runtime_check >= _WS_RUNTIME_RECHECK_SEC:
            if await _reload_credentials(endpoint_id, expected_identity) is None:
                _log_drift(endpoint_id)
                return
            last_runtime_check = loop.time()

        if not message_queue.empty():
            # Recheck immediately before forwarding a queued command; an active
            # stream may otherwise prevent recv timeouts.
            if await _reload_credentials(endpoint_id, expected_identity) is None:
                return
            last_runtime_check = loop.time()
            try:
                # Never block the event loop: a concurrent discard may have
                # drained the queue since the emptiness check.
                queued = message_queue.get_nowait()
            except Empty:
                queued = None
            command = _command_for_worker(queued, endpoint_id, expected_identity)
            if command is not None:
                await websocket.send(command)

        next_check_in = max(
            _WS_RUNTIME_RECHECK_SEC - (loop.time() - last_runtime_check),
            0.01,
        )
        try:
            response = await asyncio.wait_for(websocket.recv(), timeout=next_check_in)
        except TimeoutError:
            if await _reload_credentials(endpoint_id, expected_identity) is None:
                _log_drift(endpoint_id)
                return
            last_runtime_check = loop.time()
            continue
        publish_backend_message(response, endpoint_id=endpoint_id)


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
        await _run_connected_session(websocket, endpoint_id, expected_identity)


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
    global websocket_task, websocket_task_identity
    with websocket_lock:
        if websocket_task_identity is None:
            return False
        if endpoint_id is not None and websocket_task_identity[0] != endpoint_id:
            return False
        task = websocket_task
        websocket_task = None
        websocket_task_identity = None
        if task is not None and not task.done():
            task.cancel()
        _discard_pending_commands_locked()
        return True


@dataclass(frozen=True, slots=True)
class MessagePage:
    """One cursor read of buffered backend messages for a single endpoint."""

    messages: list[str]
    next_sequence: int
    gap: bool


def _append_message_locked(message: str, endpoint_id: int) -> int:
    """Append one message; the caller must hold ``websocket_lock``."""
    global _last_sequence, _last_sync_activity
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


def _release_command_locked(queued: object) -> None:
    """Release the button of a command that will never be sent."""
    if isinstance(queued, QueuedCommand):
        kind = _COMMAND_TO_KIND.get(queued.command)
        if kind is not None:
            ws_sync_button_state[kind] = "not-started"


def _command_for_worker(
    queued: object, endpoint_id: int, expected_identity: str
) -> str | None:
    """Return the command to send, or ``None`` after dropping a foreign one."""
    if queued is None:
        return None
    if (
        isinstance(queued, QueuedCommand)
        and queued.endpoint_id == endpoint_id
        and queued.identity == expected_identity
    ):
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


def send_message(message: str, *, endpoint_id: int, identity: str) -> None:
    """Enqueue a string command for the background WebSocket client to send upstream."""
    if message_queue.qsize() >= _MAX_MESSAGE_QUEUE_SIZE:
        logger.warning(
            "Message queue full (%d), dropping message", _MAX_MESSAGE_QUEUE_SIZE
        )
        return
    message_queue.put(
        QueuedCommand(endpoint_id=endpoint_id, identity=identity, command=message)
    )


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

        with websocket_lock:
            identity = websocket_task_identity
            if identity is None or identity[0] != endpoint_pk:
                # The authorized worker was stopped or replaced after the
                # permission check; never queue for a different endpoint.
                return JsonResponse(
                    {"error": "The WebSocket worker changed; retry the request."},
                    status=409,
                )
            # Capture the cursor in the same critical section as the state
            # transition, so a terminal published concurrently is either
            # before the cursor (and its button already released) or after it.
            cursor = format_message_cursor(_last_sequence)
            # One sync at a time: terminals carry no run identifier, so
            # overlapping kinds could release each other's latch.
            _expire_idle_sync_latch_locked()
            queued = all(
                state == "not-started" for state in ws_sync_button_state.values()
            )
            if queued:
                ws_sync_button_state[message] = "syncing"
                _mark_sync_activity_locked()
                send_message(command, endpoint_id=identity[0], identity=identity[1])
        return JsonResponse(
            {"kind": message, "queued": queued, "cursor": cursor},
            status=202 if queued else 409,
        )
