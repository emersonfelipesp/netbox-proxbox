"""Bridge browser polling requests to the backend WebSocket message stream."""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from collections import deque
from concurrent.futures import Future
from dataclasses import dataclass
from hashlib import sha256
from queue import Queue

import websockets
import websockets.exceptions
from asgiref.sync import sync_to_async
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views import View

from netbox_proxbox.models import FastAPIEndpoint
from netbox_proxbox.utils import get_fastapi_url
from netbox_proxbox.views.proxbox_access import permission_view_fastapi_endpoint
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

GLOBAL_WEBSOCKET_MESSAGES = deque(maxlen=500)
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


@dataclass(frozen=True, slots=True)
class _WebSocketCredentials:
    """Ephemeral credentials loaded for one trusted WebSocket connection."""

    uri: str
    api_key: str
    identity: str


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


async def websocket_client(endpoint_id: int, expected_identity: str) -> None:
    """Maintain a WebSocket only while the endpoint remains exactly trusted."""
    reconnect_delay = _RECONNECT_DELAY_SEC
    while True:
        credentials = await sync_to_async(
            _load_websocket_credentials,
            thread_sensitive=True,
        )(endpoint_id, expected_identity)
        if credentials is None:
            logger.info(
                "Stopping Proxbox plugin WebSocket for endpoint %s after configuration drift",
                endpoint_id,
            )
            return
        try:
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
                # The handshake can take several seconds. Reload immediately
                # before sending the key so a save/disable during connect cannot
                # emit the stale credential once.
                current = await sync_to_async(
                    _load_websocket_credentials,
                    thread_sensitive=True,
                )(endpoint_id, expected_identity)
                if current is None:
                    return
                credentials = current
                logger.info(
                    "Proxbox plugin WebSocket connected for endpoint %s",
                    endpoint_id,
                )
                await websocket.send(json.dumps({"api_key": credentials.api_key}))
                reconnect_delay = _RECONNECT_DELAY_SEC
                last_runtime_check = asyncio.get_running_loop().time()
                while True:
                    now = asyncio.get_running_loop().time()
                    if now - last_runtime_check >= _WS_RUNTIME_RECHECK_SEC:
                        current = await sync_to_async(
                            _load_websocket_credentials,
                            thread_sensitive=True,
                        )(endpoint_id, expected_identity)
                        if current is None:
                            logger.info(
                                "Stopping Proxbox plugin WebSocket for endpoint %s "
                                "after configuration drift",
                                endpoint_id,
                            )
                            return
                        last_runtime_check = now

                    if not message_queue.empty():
                        # Recheck immediately before forwarding a queued command;
                        # an active stream may otherwise prevent recv timeouts.
                        current = await sync_to_async(
                            _load_websocket_credentials,
                            thread_sensitive=True,
                        )(endpoint_id, expected_identity)
                        if current is None:
                            return
                        last_runtime_check = asyncio.get_running_loop().time()
                        new_message = message_queue.get()
                        await websocket.send(new_message)

                    next_check_in = max(
                        _WS_RUNTIME_RECHECK_SEC
                        - (asyncio.get_running_loop().time() - last_runtime_check),
                        0.01,
                    )
                    try:
                        response = await asyncio.wait_for(
                            websocket.recv(),
                            timeout=next_check_in,
                        )
                    except TimeoutError:
                        current = await sync_to_async(
                            _load_websocket_credentials,
                            thread_sensitive=True,
                        )(endpoint_id, expected_identity)
                        if current is None:
                            logger.info(
                                "Stopping Proxbox plugin WebSocket for endpoint %s "
                                "after configuration drift",
                                endpoint_id,
                            )
                            return
                        last_runtime_check = asyncio.get_running_loop().time()
                        continue
                    try:
                        response_dict = json.loads(response)
                        with websocket_lock:
                            if (
                                response_dict.get("object") == "device"
                                and response_dict.get("end") is True
                            ):
                                ws_sync_button_state["devices"] = "not-started"
                            if (
                                response_dict.get("object") == "virtual_machine"
                                and response_dict.get("end") is True
                            ):
                                ws_sync_button_state["virtual-machines"] = "not-started"
                            if (
                                response_dict.get("object") == "full-update"
                                and response_dict.get("end") is True
                            ):
                                ws_sync_button_state["full-update"] = "not-started"
                    except json.JSONDecodeError:
                        logger.debug("Received a non-JSON backend WebSocket message")

                    with websocket_lock:
                        GLOBAL_WEBSOCKET_MESSAGES.append(response)
        except asyncio.CancelledError:
            raise
        except websockets.exceptions.ConnectionClosed as exc:
            logger.warning(
                "WebSocket closed (code=%s); reconnecting in %ss",
                getattr(exc, "code", None),
                reconnect_delay,
            )
            await asyncio.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, _RECONNECT_MAX_DELAY_SEC)
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
            await asyncio.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, _RECONNECT_MAX_DELAY_SEC)
        except OSError as exc:
            logger.warning(
                "WebSocket connect error (%s) for endpoint %s; retrying in %ss",
                type(exc).__name__,
                endpoint_id,
                reconnect_delay,
            )
            await asyncio.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, _RECONNECT_MAX_DELAY_SEC)
        except (KeyboardInterrupt, SystemExit, GeneratorExit):
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Unexpected WebSocket error (%s) for endpoint %s; retrying in %ss",
                type(exc).__name__,
                endpoint_id,
                reconnect_delay,
            )
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
        return True


def send_message(message: str) -> None:
    """Enqueue a string command for the background WebSocket client to send upstream."""
    if message_queue.qsize() >= _MAX_MESSAGE_QUEUE_SIZE:
        logger.warning(
            "Message queue full (%d), dropping message", _MAX_MESSAGE_QUEUE_SIZE
        )
        return
    message_queue.put(message)


class WebSocketView(
    TokenConditionalLoginRequiredMixin,
    ContentTypePermissionRequiredMixin,
    View,
):
    """Poll recent backend WebSocket messages or trigger sync commands via the shared client."""

    template_name = "netbox_proxbox/websocket_page.html"

    def get_required_permission(self) -> str:
        """Require FastAPI endpoint view permission to read backend stream state."""
        return permission_view_fastapi_endpoint()

    def get(self, request: HttpRequest, message: str) -> HttpResponse:
        """Drain buffered messages, ensure the WS client is running, optionally kick off a sync kind."""
        json_response = request.GET.get("json_response", "false").lower() == "true"
        bulk_messages_count = 20

        fastapi_object = (
            FastAPIEndpoint.objects.filter(
                enabled=True,
                use_websocket=True,
                server_side_websocket=True,
            )
            .order_by("pk")
            .first()
        )
        if fastapi_object is None or not bool(
            getattr(fastapi_object, "enabled", False)
        ):
            return HttpResponse("Enabled FastAPIEndpoint object not found", status=404)

        fastapi_detail = get_fastapi_url(fastapi_object) or {}
        if not isinstance(fastapi_detail, dict):
            fastapi_detail = {}

        uri = fastapi_detail.get("server_websocket_url")
        if not uri:
            return HttpResponse("WebSocket URL not found", status=404)

        if not start_websocket(int(fastapi_object.pk)):
            return HttpResponse("Trusted WebSocket configuration not found", status=404)

        global GLOBAL_WEBSOCKET_MESSAGES

        with websocket_lock:
            drain_count = min(bulk_messages_count, len(GLOBAL_WEBSOCKET_MESSAGES))
            messages_to_render = [
                GLOBAL_WEBSOCKET_MESSAGES.popleft() for _ in range(drain_count)
            ]

        with websocket_lock:
            if (
                message == "full-update"
                and ws_sync_button_state["full-update"] == "not-started"
            ):
                ws_sync_button_state["full-update"] = "syncing"
                send_message("Full Update")
            elif (
                message == "devices"
                and ws_sync_button_state["devices"] == "not-started"
            ):
                ws_sync_button_state["devices"] = "syncing"
                send_message("Sync Nodes")
            elif (
                message == "virtual-machines"
                and ws_sync_button_state["virtual-machines"] == "not-started"
            ):
                ws_sync_button_state["virtual-machines"] = "syncing"
                send_message("Sync Virtual Machines")

        if json_response:
            return JsonResponse(messages_to_render, safe=False)

        return render(request, self.template_name, {"messages": messages_to_render})
