import asyncio
import websockets
from asgiref.sync import async_to_sync, sync_to_async
from netbox_proxbox.views import get_fastapi_url
from netbox_proxbox.models import FastAPIEndpoint
from django.shortcuts import render
from django.http import HttpResponse
import datetime
from django.views import View
import threading

GLOBAL_WEBSOCKET_MESSAGES = []
websocket_task = None

async def websocket_client(uri):
    try:
        print(f'Connecting with websocket server: {uri}')
        async with websockets.connect(f'{uri}') as websocket:
            await websocket.send("Hello, server!")
            while True:
                response = await websocket.recv()
                GLOBAL_WEBSOCKET_MESSAGES.append(response)
                print('GLOBAL_WEBSOCKET_MESSAGES:', GLOBAL_WEBSOCKET_MESSAGES)
    except Exception as e:
        print(f'WebSocket connection error: {e}')

def start_websocket(uri):
    global websocket_task
    if websocket_task is None or websocket_task.done():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        websocket_task = loop.create_task(websocket_client(uri))
        threading.Thread(target=loop.run_forever).start()
        print('WebSocket task started.')

def stop_websocket():
    global websocket_task
    if websocket_task:
        websocket_task.cancel()
        print('WebSocket task stopped.')

class WebSocketView(View):
    template_name = 'netbox_proxbox/websocket_client.html'
    
    def get(self, request):
        # Use sync_to_async to call synchronous Django ORM operations
        fastapi_object = FastAPIEndpoint.objects.first()
        if fastapi_object is None:
            return HttpResponse("FastAPIEndpoint object not found", status=404)
        
        uri = get_fastapi_url(fastapi_object).get('websocket_url')
        if uri is None:
            return HttpResponse("WebSocket URL not found", status=404)
        
        start_websocket(uri)
        print('GLOBAL_WEBSOCKET_MESSAGES:', GLOBAL_WEBSOCKET_MESSAGES)
        print(websocket_task)
        
        return render(
            request,
            self.template_name,
            {
                'messages': GLOBAL_WEBSOCKET_MESSAGES
            }
        )