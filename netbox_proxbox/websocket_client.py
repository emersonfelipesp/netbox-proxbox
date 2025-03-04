import asyncio
import websockets
from asgiref.sync import async_to_sync, sync_to_async
from netbox_proxbox.views import get_fastapi_url
from netbox_proxbox.models import FastAPIEndpoint

from django.http import HttpResponse
import datetime

async def websocket_client(request): 
    # Use sync_to_async to call synchronous Django ORM operations
    fastapi_object = await sync_to_async(FastAPIEndpoint.objects.first)()
    if fastapi_object is None:
        return HttpResponse("FastAPIEndpoint object not found", status=404)
    
    uri = get_fastapi_url(fastapi_object).get('websocket_url')
    if uri is None:
        return HttpResponse("WebSocket URL not found", status=404)
    
    #uri = 'ws://127.0.0.1:8001'
    print(f'Connecting with websocket server: {uri}')
    async with websockets.connect(f'{uri}') as websocket:
        await websocket.send("Hello, server!")
        response = await websocket.recv()
        return HttpResponse(response)