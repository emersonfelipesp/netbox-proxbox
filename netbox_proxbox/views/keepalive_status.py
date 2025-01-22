# Django Imports
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET
from django.urls import reverse
import requests

# Django-HTMX Imports

from django_htmx.middleware import HtmxDetails
from django_htmx.http import replace_url

class HtmxHttpRequest(HttpRequest):
    htmx: HtmxDetails

from netbox_proxbox.models import *

@require_GET
def get_service_status(
    request: HtmxHttpRequest,
    service: str,
    pk: int,
) -> HttpResponse:
    """Get the status of a service."""
    template_name: str = 'netbox_proxbox/status_badge.html'
    
    # Accept only HTMX requests to render this view.
    if not request.htmx:
        return HttpResponse(status=400)
    
    host: str = ''
    url: str = ''
    status: str = 'unknown'
    
    if service == 'fastapi':
        fastapi_service_obj = FastAPIEndpoint.objects.get(pk=pk)
    else:
        fastapi_service_obj = FastAPIEndpoint.objects.first()
    
    if fastapi_service_obj:
        host = str(fastapi_service_obj.ip_address.address).split('/')[0]
        url: str = f"http://{host}:{fastapi_service_obj.port}/"
    
    if service == 'proxmox':
        proxmox_service_obj = ProxmoxEndpoint.objects.get(pk=pk)
            
        if proxmox_service_obj:
            proxmox_host: str = str(proxmox_service_obj.ip_address).split('/')[0]
            url = f'{url}/proxmox/version?domain={proxmox_host}'
        
    if service == 'netbox':
        netbox_service_obj = NetBoxEndpoint.objects.get(pk=pk)
        url = f'{url}/netbox/status'
        
    try:
        response = requests.get(url)
        response.raise_for_status()
        status = 'success'
        
    except requests.exceptions.HTTPError as err:
        print(f'HTTP error ocrrured: {err}')
        status = 'error'
        
    except Exception as errr:
        print(f'Error ocurred: {errr}')
        status = 'error'
    
    return render(
        request,
        template_name,
        {
            'status': status
        }
    )
 