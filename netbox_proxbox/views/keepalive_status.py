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

CONNECTED_URL_SUCCESSFUL = None

def fastapi_status(pk: int) -> dict:
    global CONNECTED_URL_SUCCESSFUL
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
                CONNECTED_URL_SUCCESSFUL = fastapi_url
            except Exception as errr:
                print(f'Error ocurred: {errr}')
                
                # Try to connect to FastAPI using the IP address and port.
                print(f'Trying to connect to FastAPI using the IP address and port: {fastapi_detail.get("ip_address_url")}')
                response = requests.get(fastapi_detail.get('ip_address_url'), verify=False)
                print(f'FastAPI response: {response.json()}')
                connected = True
                CONNECTED_URL_SUCCESSFUL = fastapi_detail.get('ip_address_url')
            '''
            except requests.exceptions.HTTPError as err:
                print(f'HTTP error ocurred: {err}')
                response = requests.get(fastapi_detail.get('ip_address_url'), verify=False)
                print(f'FastAPI response: {response.json()}')
                response.raise_for_status()
                connected = True
            '''
            
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
    default_netbox_ip = "127.0.0.1"
    netbox_ip = default_netbox_ip
    try:
        netbox_ipaddress_obj = getattr(netbox_service_obj,  "ip_address", None)
        if netbox_ipaddress_obj:
            netbox_ip = getattr(netbox_ipaddress_obj, "address")
            netbox_ip = netbox_ip.split('/')[0] if netbox_ip else default_netbox_ip
    except Exception as err:
        print(f"Error getting NetBoxEndpoint IP address: {err}. Using default IP address: {default_netbox_ip}")
        netbox_ip = default_netbox_ip
    
    # Define NetBoxEndpoint URL to get endpoints from pynetbox-api database (sqlite)
    netbox_endpoint_url: str = f'{base_url}/netbox/endpoint'
    netbox_status_route: str = f'{base_url}/netbox/status'
    
    try:
        # Check if NetBoxEndpoint exists on FastAPI database.
        response = requests.get(netbox_endpoint_url)
        response.raise_for_status()
        response = list(response.json())
        
        netbox = None
        
        token_obj = getattr(netbox_service_obj, 'token', None)
        token_key = getattr(token_obj, 'key', None) if token_obj else 'invalid-token'
        
        current_netbox: dict = {
            'id': pk,
            'name': netbox_service_obj.name if netbox_service_obj.name else None,
            'ip_address': netbox_ip,
            'domain': netbox_service_obj.domain if netbox_service_obj.domain else None,
            'port': netbox_service_obj.port if netbox_service_obj.port else None,
            'token': token_key,
            'verify_ssl': netbox_service_obj.verify_ssl if netbox_service_obj.verify_ssl else False,
        }
        
        # If no NetBoxEndpoints are found on FastAPI database, create a new one.
        if len(response) == 0:
            print('No NetBoxEndpoints found on FastAPI database.')
            
            # Create NetBoxEndpoint on FastAPI database.
            print('Creating NetBoxEndpoint on FastAPI database...')
            print(f'current_netbox: {current_netbox}')
            print(f'netbox_endpoint_url: {netbox_endpoint_url}')
            requests.post(netbox_endpoint_url, json=current_netbox)
        
        if len(response) > 0:
            # Delete all NetBoxEndpoints from FastAPI database, except the one that matches the current NetBoxEndpoint.
            for netbox_endpoint in response:
                if netbox_endpoint['id'] != pk:
                    requests.delete(f'{netbox_endpoint_url}/{netbox_endpoint["id"]}')
                else:
                    # If NetBox ID exists, update it (if needed)
                    if netbox_endpoint != current_netbox:
                        updated_netbox_endpoint: dict = netbox_endpoint | current_netbox
                        requests.delete(f'{netbox_endpoint_url}/{netbox_endpoint["id"]}') 
                        requests.post(netbox_endpoint_url, json=updated_netbox_endpoint)
            
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
        proxmox_ip_address: str = str(proxmox_service_obj.ip_address).split('/')[0]
        proxmox_domain: str = proxmox_service_obj.domain if proxmox_service_obj.domain else None
        
        url = None
        if proxmox_domain:
            url = f'{base_url}/proxmox/version?domain={proxmox_domain}'
        
        if not proxmox_domain and proxmox_ip_address:
            url = f'{base_url}/proxmox/version?ip_address={proxmox_ip_address}'
        
        
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
    global CONNECTED_URL_SUCCESSFUL
    
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
        netbox_response = netbox_status(pk=pk, base_url=CONNECTED_URL_SUCCESSFUL)
        status = netbox_response if netbox_response is not None else 'error'

    if service == 'proxmox' and fastapi_response.get('connected') == True:
        print('Trying to get Proxmox status...')
        proxmox_response = proxmox_status(pk=pk, base_url=CONNECTED_URL_SUCCESSFUL)
        status = proxmox_response if proxmox_response is not None else 'error'
    
    return render(
        request,
        template_name,
        {
            'status': status
        }
    )
 