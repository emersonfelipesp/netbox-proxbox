"""Bridge browser polling requests to the backend WebSocket message stream."""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from collections import deque
from queue import Queue

import websockets
import websockets.exceptions
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
_MAX_MESSAGE_QUEUE_SIZE = 1000

GLOBAL_WEBSOCKET_MESSAGES = deque(maxlen=500)
websocket_task = None
websocket_loop = None
websocket_lock = threading.Lock()
message_queue = Queue()
ws_sync_button_state = {
    "full-update": "not-started",
    "devices": "not-started",
    "virtual-machines": "not-started",
}


async def websocket_client(uri: str) -> None:
    """Maintain a long-lived WebSocket to the ProxBox backend; reconnect with backoff."""
    reconnect_delay = _RECONNECT_DELAY_SEC
    while True:
        try:
            async with websockets.connect(
                uri, open_timeout=_WS_CONNECTION_TIMEOUT
            ) as websocket:
                logger.info("Proxbox plugin WebSocket connected: %s", uri)
                while True:
                    if not message_queue.empty():
                        new_message = message_queue.get()
                        await websocket.send(new_message)

                    response = await websocket.recv()
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
                        logger.debug(
                            "Non-JSON WebSocket message (first 200 chars): %r",
                            (response[:200] if isinstance(response, str) else response),
                        )

                    with websocket_lock:
                        GLOBAL_WEBSOCKET_MESSAGES.append(response)
        except websockets.exceptions.ConnectionClosed as exc:
            logger.warning(
                "WebSocket closed (code=%s reason=%r); reconnecting in %ss",
                getattr(exc, "code", None),
                getattr(exc, "reason", ""),
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
                    uri,
                )
                return
            logger.warning(
                "WebSocket handshake failed (HTTP %s) for %s; retrying in %ss",
                status_code,
                uri,
                reconnect_delay,
            )
            await asyncio.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, _RECONNECT_MAX_DELAY_SEC)
        except OSError as exc:
            logger.warning(
                "WebSocket connect error for %s: %s; retrying in %ss",
                uri,
                exc,
                reconnect_delay,
            )
            await asyncio.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, _RECONNECT_MAX_DELAY_SEC)
        except (KeyboardInterrupt, SystemExit, GeneratorExit):
            raise
        except Exception:
            logger.exception(
                "Unexpected WebSocket error for %s; retrying in %ss",
                uri,
                reconnect_delay,
            )
            await asyncio.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, _RECONNECT_MAX_DELAY_SEC)


def start_websocket(uri: str) -> None:
    """Start a daemon thread and asyncio loop running ``websocket_client`` for ``uri`` if not already running."""
    global websocket_task, websocket_loop
    with websocket_lock:
        if websocket_task is not None and not websocket_task.done():
            return

        websocket_loop = asyncio.new_event_loop()

        def run_loop() -> None:
            asyncio.set_event_loop(websocket_loop)
            websocket_loop.run_forever()

        thread = threading.Thread(target=run_loop, daemon=True)
        thread.start()
        websocket_task = asyncio.run_coroutine_threadsafe(
            websocket_client(uri), websocket_loop
        )


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

        global GLOBAL_WEBSOCKET_MESSAGES

        with websocket_lock:
            drain_count = min(bulk_messages_count, len(GLOBAL_WEBSOCKET_MESSAGES))
            messages_to_render = [
                GLOBAL_WEBSOCKET_MESSAGES.popleft() for _ in range(drain_count)
            ]

        fastapi_object = FastAPIEndpoint.objects.first()
        if fastapi_object is None:
            return HttpResponse("FastAPIEndpoint object not found", status=404)

        fastapi_detail = get_fastapi_url(fastapi_object) or {}
        if not isinstance(fastapi_detail, dict):
            fastapi_detail = {}

        uri = fastapi_detail.get("websocket_url")
        if uri is None:
            return HttpResponse("WebSocket URL not found", status=404)

        start_websocket(uri)

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
