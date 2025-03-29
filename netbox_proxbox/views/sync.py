import requests

# Django Imports
from django.http import HttpRequest, HttpResponse
from django.views import View
from django.views.decorators.http import require_GET
from django.shortcuts import render

# Django-HTMX Imports
from django_htmx.middleware import HtmxDetails

# Proxbox Imports
from netbox_proxbox.utils import get_fastapi_url
from netbox_proxbox.models import FastAPIEndpoint

from threading import Thread


class HtmxHttpRequest(HttpRequest):
    htmx: HtmxDetails

CONNECTED_URL_SUCCESSFUL = None

fastapi_service_obj = None
# Get the first FastAPI Endpoint object
try:
    fastapi_service_obj = FastAPIEndpoint.objects.first()
except Exception as errr:
    print(f'Error occurred getting FastAPI Endpoint object: {errr}')

if fastapi_service_obj:
    # Get the FastAPI URL
    fastapi_detail = get_fastapi_url(fastapi_service_obj)
    fastapi_url: str = fastapi_detail.get('http_url', None)
    fastapi_verify_ssl: bool = fastapi_detail.get('verify_ssl', True)

def sync_resource(request: HtmxHttpRequest, path: str, template_name: str) -> HttpResponse:
    global CONNECTED_URL_SUCCESSFUL

    fastapi_path: str = f'{fastapi_url}/{path}' if fastapi_url else None

    if not fastapi_url:
        return HttpResponse(status=404, content='No FastAPI URL found')

    def make_request():
        try:
            response = requests.get(fastapi_path, verify=fastapi_verify_ssl)
            print(f'FastAPI response: {response.json()}')
            response.raise_for_status()
            CONNECTED_URL_SUCCESSFUL = fastapi_url
        except Exception as errr:
            print(f'Error occurred: {errr}')

            # Try to connect to FastAPI using the IP address and port.
            print(f'Trying to connect to FastAPI using the IP address and port: {fastapi_detail.get("ip_address_url")}')
            response = requests.get(fastapi_detail.get('ip_address_url') + f'/{path}', verify=False)
            print(f'FastAPI response: {response.json()}')
            CONNECTED_URL_SUCCESSFUL = fastapi_detail.get('ip_address_url')

    # Run the request in a separate thread
    Thread(target=make_request).start()

    return render(request, template_name)

@require_GET
def sync_devices(request: HtmxHttpRequest) -> HttpResponse:
    return sync_resource(request, 'dcim/devices/create', 'netbox_proxbox/sync_devices.html')

@require_GET
def sync_virtual_machines(request: HtmxHttpRequest) -> HttpResponse:
    return sync_resource(request, 'virtualization/virtual-machines/create', 'netbox_proxbox/sync_virtual_machines.html')

@require_GET
def sync_full_update(request: HtmxHttpRequest) -> HttpResponse:
    return sync_resource(request, 'full-update', 'netbox_proxbox/sync_full_update.html')