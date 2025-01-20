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
    obj = None
) -> HttpResponse:
    """Get the status of a service."""
    template_name: str = 'netbox_proxbox/status_badge.html'
    
    if not request.htmx:
        return HttpResponse(status=400)
    
    status: str = 'unknown'
    
    if service == 'fastapi':
        fastapi_service_obj = FastAPIEndpoint.objects.first()
        host = str(fastapi_service_obj.ip_address.address).split('/')[0]
        url: str = f"https://{host}:{fastapi_service_obj.port}/"
        
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
 