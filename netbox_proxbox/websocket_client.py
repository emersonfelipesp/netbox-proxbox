"""Bridge browser polling requests to the backend WebSocket message stream."""

from __future__ import annotations

import asyncio
import json
import threading
from queue import Queue

import websockets
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views import View

from netbox_proxbox.models import FastAPIEndpoint
from netbox_proxbox.utils import get_fastapi_url


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


async def websocket_client(uri):
    try:
        async with websockets.connect(uri) as websocket:
            while True:
                if not message_queue.empty():
                    new_message = message_queue.get()
                    await websocket.send(new_message)

                response = await websocket.recv()
                try:
                    response_dict = json.loads(response)
                    if response_dict.get("object") == "device" and response_dict.get("end") is True:
                        sync_processes["devices"] = "not-started"
                    if response_dict.get("object") == "virtual_machine" and response_dict.get("end") is True:
                        sync_processes["virtual-machines"] = "not-started"
                    if response_dict.get("object") == "full-update" and response_dict.get("end") is True:
                        sync_processes["full-update"] = "not-started"
                except json.JSONDecodeError:
                    pass

                with websocket_lock:
                    GLOBAL_WEBSOCKET_MESSAGES.append(response)
    except Exception:
        await asyncio.sleep(5)
        await websocket_client(uri)


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
    websocket_task = asyncio.run_coroutine_threadsafe(websocket_client(uri), websocket_loop)


def send_message(message):
    message_queue.put(message)


class WebSocketView(View):
    template_name = "netbox_proxbox/websocket_page.html"

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

        uri = get_fastapi_url(fastapi_object).get("websocket_url")
        if uri is None:
            return HttpResponse("WebSocket URL not found", status=404)

        start_websocket(uri)

        if message == "full-update" and sync_processes["full-update"] == "not-started":
            sync_processes["full-update"] = "syncing"
            send_message("Full Update")
        elif message == "devices" and sync_processes["devices"] == "not-started":
            sync_processes["devices"] = "syncing"
            send_message("Sync Nodes")
        elif message == "virtual-machines" and sync_processes["virtual-machines"] == "not-started":
            sync_processes["virtual-machines"] = "syncing"
            send_message("Sync Virtual Machines")

        if json_response:
            return JsonResponse(messages_to_render, safe=False)

        return render(request, self.template_name, {"messages": messages_to_render})
