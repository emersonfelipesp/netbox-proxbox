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
from netbox_proxbox.utils import get_fastapi_url

def fastapi_status(pk: int) -> dict:
    connected: bool = False
    
    fastapi_service_obj = None
    try:
        fastapi_service_obj = FastAPIEndpoint.objects.get(pk=pk)
    except FastAPIEndpoint.DoesNotExist:
        fastapi_service_obj = FastAPIEndpoint.objects.first()
        
    if fastapi_service_obj:
        fastapi_detail = get_fastapi_url(fastapi_service_obj)
        fastapi_url: str = fastapi_detail.get('http_url')
        fastapi_verify_ssl: bool = fastapi_detail.get('verify_ssl', True)

        print(f'FastAPI URL: {fastapi_url}')
        
        if fastapi_url:
            try:
                response = requests.get(fastapi_url, verify=fastapi_verify_ssl)
                print(f'FastAPI response: {response.json()}')
                response.raise_for_status()
                connected = True
            except requests.exceptions.HTTPError as err:
                print(f'HTTP error ocurred: {err}')
            except Exception as errr:
                print(f'Error ocurred: {errr}')
    
    return {
        'url': fastapi_url,
        'connected': connected
    }
    
def netbox_status(pk: int, base_url: str) -> str:
    netbox_service_obj = None
    status = 'error'
    
    try:
        # Get NetBoxEndpoint object by primary key.
        netbox_service_obj = NetBoxEndpoint.objects.get(pk=pk)
    except NetBoxEndpoint.DoesNotExist:
        return status
    
    # Get NetBoxEndpoint IP address.
    netbox_ip = str(netbox_service_obj.ip_address.address).split('/')[0]
    
    # Define NetBoxEndpoint URL to get endpoints from pynetbox-api database (sqlite)
    netbox_endpoint_url: str = f'{base_url}/netbox/endpoint'
    netbox_status_route: str = f'{base_url}/netbox/status'
    
    try:
        # Check if NetBoxEndpoint exists on FastAPI database.
        response = requests.get(netbox_endpoint_url)
        response.raise_for_status()
        response = list(response.json())
        
        netbox = None
        
        current_netbox: dict = {
            'id': pk,
            'name': netbox_service_obj.name,
            'ip_address': netbox_ip,
            'domain': netbox_service_obj.domain,
            'port': netbox_service_obj.port,
            'token': netbox_service_obj.token,
            'verify_ssl': netbox_service_obj.verify_ssl,
        }
        
        if len(response) > 0:
            for nb in response:
                # Check if NetBoxEndpoint exists on pynetbox-api database.
                if (nb['id'] == pk) and (nb['ip_address'] == netbox_ip):
                    netbox = nb
                    break
            
            if netbox:
                # Delete all NetBoxEndpoints from FastAPI database, except the one that matches the current NetBoxEndpoint.
                for nb in response:
                    if nb['id'] != pk:
                        requests.delete(f'{netbox_endpoint_url}/{nb["id"]}')
                    else:
                        # If NetBox ID exists, update it (if needed)
                        if nb != current_netbox:
                            updated_netbox = nb | current_netbox
                            requests.delete(f'{netbox_endpoint_url}/{nb["id"]}') 
                            requests.post(netbox_endpoint_url, json=updated_netbox)
                    
            else:
                # Delete all NetBoxEndpoints from FastAPI database.
                for nb in response:
                    requests.delete(f'{netbox_endpoint_url}/{nb["id"]}')
            
        else:
            # Create NetBoxEndpoint on FastAPI database.
            print('Creating NetBoxEndpoint on FastAPI database...')
            requests.post(netbox_endpoint_url, json=current_netbox)
        
        # NetBoxEndpoint exists on FastAPI database. Check if it is alive.
        try:
            response = requests.get(netbox_status_route)
            response.raise_for_status()
            status = 'success'
        except requests.exceptions.HTTPError as err:
            print(f'HTTP error ocurred: {err}')
            status = 'error'
        except Exception as errr:
            print(f'Error ocurred: {errr}')
            status = 'error'
        
    except requests.exceptions.HTTPError as err:
        print(f'HTTP error ocurred: {err}')
        status = 'error'
    
    except Exception as errr:
        print(f'Error ocurred: {errr}')
        status = 'error'
    
    return status
    
def proxmox_status(pk: int, base_url: str) -> str:
    proxmox_service_obj = None
    status = 'error'
    
    try:
        proxmox_service_obj = ProxmoxEndpoint.objects.get(pk=pk)    
    except ProxmoxEndpoint.DoesNotExist:
        return status
        
    if proxmox_service_obj:
        proxmox_host: str = str(proxmox_service_obj.ip_address).split('/')[0]
        url = f'{base_url}/proxmox/version?ip_address={proxmox_host}&port={proxmox_service_obj.port}'
        
        if url:
            try:
                response = requests.get(url)
                print(response)
                print(response.status_code, type(response.status_code))
                response.raise_for_status()
                status = 'success'
            except requests.exceptions.HTTPError as err:
                print(f'HTTP error ocurred: {err}')
            except Exception as errr:
                print(f'Error ocurred: {errr}')
    
    print(status)
    return status

@require_GET
def get_service_status(
    request: HtmxHttpRequest,
    service: str,
    pk: int,
) -> HttpResponse:
    """Get the status of a service."""
    template_name: str = 'netbox_proxbox/status_badge.html'
    
    # Accept only HTMX requests to render this view.
    #if not request.htmx:
    #    return HttpResponse(status=400)

    status: str = 'unknown'
    fastapi_response: dict = {}
    
    if service == 'fastapi':
        fastapi_response = fastapi_status(pk)
        status = 'success' if fastapi_response.get('connected') == True else 'error'
    else:
        try:
            fastapi_response = fastapi_status(pk=FastAPIEndpoint.objects.first().id)
        except FastAPIEndpoint.DoesNotExist:
            pass
    
    if service == 'netbox' and fastapi_response.get('connected') == True:
        print('Trying to get NetBox status...')
        netbox_response = netbox_status(pk=pk, base_url=fastapi_response.get('url'))
        status = netbox_response if netbox_response is not None else 'error'

    if service == 'proxmox' and fastapi_response.get('connected') == True:
        print('Trying to get Proxmox status...')
        proxmox_response = proxmox_status(pk=pk, base_url=fastapi_response.get('url'))
        status = proxmox_response if proxmox_response is not None else 'error'
    
    return render(
        request,
        template_name,
        {
            'status': status
        }
    )
 