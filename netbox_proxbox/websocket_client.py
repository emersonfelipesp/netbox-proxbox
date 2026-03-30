"""Bridge browser polling requests to the backend WebSocket message stream."""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from queue import Queue

import websockets
import websockets.exceptions
from django.http import HttpResponse, JsonResponse
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

GLOBAL_WEBSOCKET_MESSAGES = []
websocket_task = None
websocket_loop = None
websocket_lock = threading.Lock()
message_queue = Queue()
sync_processes = {
    "full-update": "not-started",
    "devices": "not-started",
    "virtual-machines": "not-started",
}


async def websocket_client(uri: str) -> None:
    """Maintain a long-lived WebSocket to the ProxBox backend; reconnect with backoff."""
    while True:
        try:
            async with websockets.connect(uri) as websocket:
                logger.info("Proxbox plugin WebSocket connected: %s", uri)
                while True:
                    if not message_queue.empty():
                        new_message = message_queue.get()
                        await websocket.send(new_message)

                    response = await websocket.recv()
                    try:
                        response_dict = json.loads(response)
                        if (
                            response_dict.get("object") == "device"
                            and response_dict.get("end") is True
                        ):
                            sync_processes["devices"] = "not-started"
                        if (
                            response_dict.get("object") == "virtual_machine"
                            and response_dict.get("end") is True
                        ):
                            sync_processes["virtual-machines"] = "not-started"
                        if (
                            response_dict.get("object") == "full-update"
                            and response_dict.get("end") is True
                        ):
                            sync_processes["full-update"] = "not-started"
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
                _RECONNECT_DELAY_SEC,
            )
            await asyncio.sleep(_RECONNECT_DELAY_SEC)
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
                _RECONNECT_DELAY_SEC,
            )
            await asyncio.sleep(_RECONNECT_DELAY_SEC)
        except OSError as exc:
            logger.warning(
                "WebSocket connect error for %s: %s; retrying in %ss",
                uri,
                exc,
                _RECONNECT_DELAY_SEC,
            )
            await asyncio.sleep(_RECONNECT_DELAY_SEC)
        except Exception:
            logger.exception(
                "Unexpected WebSocket error for %s; retrying in %ss",
                uri,
                _RECONNECT_DELAY_SEC,
            )
            await asyncio.sleep(_RECONNECT_DELAY_SEC)


def start_websocket(uri):
    global websocket_task, websocket_loop
    if websocket_task is not None and not websocket_task.done():
        return

    websocket_loop = asyncio.new_event_loop()

    def run_loop():
        asyncio.set_event_loop(websocket_loop)
        websocket_loop.run_forever()

    thread = threading.Thread(target=run_loop, daemon=True)
    thread.start()
    websocket_task = asyncio.run_coroutine_threadsafe(
        websocket_client(uri), websocket_loop
    )


def send_message(message):
    message_queue.put(message)


class WebSocketView(
    TokenConditionalLoginRequiredMixin,
    ContentTypePermissionRequiredMixin,
    View,
):
    template_name = "netbox_proxbox/websocket_page.html"

    def get_required_permission(self):
        return permission_view_fastapi_endpoint()

    def get(self, request, message):
        json_response = request.GET.get("json_response", "false").lower() == "true"
        bulk_messages_count = 20

        global GLOBAL_WEBSOCKET_MESSAGES

        with websocket_lock:
            messages_to_render = GLOBAL_WEBSOCKET_MESSAGES[:bulk_messages_count]
            GLOBAL_WEBSOCKET_MESSAGES = GLOBAL_WEBSOCKET_MESSAGES[bulk_messages_count:]

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

        if message == "full-update" and sync_processes["full-update"] == "not-started":
            sync_processes["full-update"] = "syncing"
            send_message("Full Update")
        elif message == "devices" and sync_processes["devices"] == "not-started":
            sync_processes["devices"] = "syncing"
            send_message("Sync Nodes")
        elif (
            message == "virtual-machines"
            and sync_processes["virtual-machines"] == "not-started"
        ):
            sync_processes["virtual-machines"] = "syncing"
            send_message("Sync Virtual Machines")

        if json_response:
            return JsonResponse(messages_to_render, safe=False)

        return render(request, self.template_name, {"messages": messages_to_render})
