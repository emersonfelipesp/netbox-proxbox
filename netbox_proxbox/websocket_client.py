import asyncio
import websockets
from asgiref.sync import async_to_sync, sync_to_async
from netbox_proxbox.views import get_fastapi_url
from netbox_proxbox.models import FastAPIEndpoint
from django.shortcuts import render
from django.http import HttpResponse, JsonResponse
import threading
from django.views import View
from django_htmx.http import HttpResponseClientRedirect
from queue import Queue
import json

GLOBAL_WEBSOCKET_MESSAGES = []
websocket_task = None
websocket_lock = threading.Lock()  # Add a lock to ensure thread safety
message_queue = Queue()
sync_processes = {
    'full-update': 'not-started',
    'devices': 'not-started',
    'virtual-machines': 'not-started',
}

async def websocket_client(uri):
    print('websocket_client reached')
    try:
        print(f'Connecting with websocket server: {uri}')
        async with websockets.connect(f'{uri}') as websocket:
            while True:
                # Send new messages from the queue
                if not message_queue.empty():
                    new_message = message_queue.get()
                    
                    if new_message == 'Sync Nodes':
                        print(f'Sending message: {new_message}')
                        await websocket.send(new_message)
                        sync_processes['devices'] = 'syncing'
                    
                    print(f'Sending message: {new_message}')
                    await websocket.send(new_message)

                response = await websocket.recv()
                response_dict = {}
                try:
                    # Convert the response to a dictionary
                    response_dict = json.loads(response)
                except json.JSONDecodeError:
                    pass
                
                print(f'response_type: {type(response)}')
                if response_dict:
                    print(f'response_dict: {response_dict}')
                    if all([
                        response_dict.get('object') == 'device',  # Checks if 'object' key exists and is 'device'
                        response_dict.get('end') == True,  # Ensures 'end' key exists and has a truthy value
                        sync_processes.get('devices') == 'syncing'  # Ensures 'devices' exists and is 'syncing'
                    ]):
                        sync_processes['devices'] = 'not-started'
                
                with websocket_lock:
                    GLOBAL_WEBSOCKET_MESSAGES.append(response)
                print('GLOBAL_WEBSOCKET_MESSAGES:', GLOBAL_WEBSOCKET_MESSAGES)
    except Exception as e:
        print(f'WebSocket connection error: {e}')
        await asyncio.sleep(5)  # Wait for 5 seconds before attempting to reconnect
        await websocket_client(uri)

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

def send_message(message):
    message_queue.put(message)

class WebSocketView(View):
    template_name = 'netbox_proxbox/websocket_page.html'
    htmx_template_name = 'netbox_proxbox/partials/websocket_messages.html'
    
    def get(self, request, message):
        print(f'sync_processes: {sync_processes}')
        print(message_queue)
        
        
        # Access `json_response` from kwargs
        json_response = request.GET.get('json_response', 'false').lower() == 'true'
        print(f'message: {message}')
        print(f'json_response: {json_response}')
        
        bulk_messages_count = 20
        # Declare the global variable to store the messages
        global GLOBAL_WEBSOCKET_MESSAGES
        global websocket_task
        
        # Ensure thread safety for message access
        with websocket_lock:
            # Get the first 20 messages
            messages_to_render = GLOBAL_WEBSOCKET_MESSAGES[:bulk_messages_count]
            
            # After saving the first 20 messages, remove them from the list
            GLOBAL_WEBSOCKET_MESSAGES = GLOBAL_WEBSOCKET_MESSAGES[bulk_messages_count:]
        
        # Use sync_to_async to call synchronous Django ORM operations
        fastapi_object = FastAPIEndpoint.objects.first()
        if fastapi_object is None:
            return HttpResponse("FastAPIEndpoint object not found", status=404)
        
        uri = get_fastapi_url(fastapi_object).get('websocket_url')
        if uri is None:
            return HttpResponse("WebSocket URL not found", status=404)
        
        # Start websocket only if not already running
        if not websocket_task or websocket_task.done():
            start_websocket(uri)
        
        # Send the initial message
        if message == 'full-update' and sync_processes.get('full-update') == 'not-started':
            sync_processes['full-update'] = 'syncing'
            send_message('Full Update')
        elif message == 'devices' and sync_processes.get('devices') == 'not-started':
            send_message('Sync Nodes')
        elif message == 'virtual-machines' and sync_processes.get('virtual-machines') == 'not-started':
            sync_processes['virtual-machines'] = 'syncing'
            send_message('Sync Virtual Machines')
        

        print('GLOBAL_WEBSOCKET_MESSAGES:', GLOBAL_WEBSOCKET_MESSAGES)
        print(websocket_task)
        
        context = {
            'messages': messages_to_render,
        }
        
        if json_response:
            # safe=False is used to allow non-dict objects to be serialized
            return JsonResponse(messages_to_render, safe=False)
        
        if request.htmx:
            # Return partial update for HTMX request
            return render(request, self.htmx_template_name, context)
        else:
            # Return full page render for non-HTMX request
            return render(request, self.template_name, context)
