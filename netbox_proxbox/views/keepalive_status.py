# Django Imports
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET
from django.urls import reverse
import requests
import time
import logging

# Django-HTMX Imports
from django_htmx.middleware import HtmxDetails
from django_htmx.http import replace_url

class HtmxHttpRequest(HttpRequest):
    htmx: HtmxDetails

from netbox_proxbox.models import *
from netbox_proxbox.utils import get_fastapi_url

logger = logging.getLogger(__name__)

class ServiceStatus:
    def __init__(self):
        self.connected_url = None

    def fastapi_status(self, pk: int) -> dict:
        connected: bool = False
        fastapi_url = None
        
        try:
            fastapi_service_obj = FastAPIEndpoint.objects.get(pk=pk)
        except FastAPIEndpoint.DoesNotExist:
            logger.warning(f"FastAPI endpoint with pk={pk} not found")
            return {'url': None, 'connected': False}
        
        fastapi_detail = get_fastapi_url(fastapi_service_obj)
        fastapi_url = fastapi_detail.get('http_url')
        fastapi_verify_ssl = fastapi_detail.get('verify_ssl', True)
        
        logger.info(f'Checking FastAPI status at {fastapi_url} with SSL verification: {fastapi_verify_ssl}')
        
        if fastapi_url:
            try:
                response = requests.get(fastapi_url, verify=fastapi_verify_ssl)
                response.raise_for_status()
                connected = True
                self.connected_url = fastapi_url
                logger.info(f'Successfully connected to FastAPI at {fastapi_url}')
            except requests.exceptions.SSLError as e:
                logger.warning(f'SSL error connecting to {fastapi_url}: {e}')
                # Try with IP address as fallback
                ip_url = fastapi_detail.get('ip_address_url')
                if ip_url:
                    try:
                        response = requests.get(ip_url, verify=False)
                        response.raise_for_status()
                        connected = True
                        self.connected_url = ip_url
                        logger.info(f'Successfully connected to FastAPI at {ip_url} (fallback)')
                    except requests.exceptions.RequestException as e:
                        logger.error(f'Failed to connect to FastAPI at {ip_url}: {e}')
            except requests.exceptions.RequestException as e:
                logger.error(f'Error connecting to FastAPI at {fastapi_url}: {e}')
        
        return {
            'url': fastapi_url,
            'connected': connected
        }
    
    def netbox_status(self, pk: int, base_url: str) -> str:
        status = 'error'
        max_retries = 3
        retry_delay = 1  # seconds
        
        try:
            netbox_service_obj = NetBoxEndpoint.objects.get(pk=pk)
        except NetBoxEndpoint.DoesNotExist:
            logger.error(f"NetBox endpoint with pk={pk} not found")
            return status
        
        # Get NetBoxEndpoint IP address
        default_netbox_ip = "127.0.0.1"
        netbox_ip = default_netbox_ip
        try:
            netbox_ipaddress_obj = getattr(netbox_service_obj, "ip_address", None)
            if netbox_ipaddress_obj:
                netbox_ip = getattr(netbox_ipaddress_obj, "address")
                netbox_ip = netbox_ip.split('/')[0] if netbox_ip else default_netbox_ip
        except Exception as e:
            logger.warning(f"Error getting NetBoxEndpoint IP address: {e}. Using default IP address: {default_netbox_ip}")
            netbox_ip = default_netbox_ip
        
        netbox_endpoint_url = f'{base_url}/netbox/endpoint'
        netbox_status_route = f'{base_url}/netbox/status'
        
        token_obj = getattr(netbox_service_obj, 'token', None)
        token_key = getattr(token_obj, 'key', None) if token_obj else 'invalid-token'
        
        current_netbox = {
            'id': pk,
            'name': netbox_service_obj.name if netbox_service_obj.name else None,
            'ip_address': netbox_ip,
            'domain': netbox_service_obj.domain if netbox_service_obj.domain else None,
            'port': netbox_service_obj.port if netbox_service_obj.port else None,
            'token': token_key,
            'verify_ssl': netbox_service_obj.verify_ssl if netbox_service_obj.verify_ssl else False,
        }
        
        for attempt in range(max_retries):
            try:
                # Check if NetBoxEndpoint exists
                response = requests.get(netbox_endpoint_url)
                response.raise_for_status()
                endpoints = list(response.json())
                
                if len(endpoints) == 0:
                    logger.info(f'Creating new NetBox endpoint: {current_netbox}')
                    create_response = requests.post(netbox_endpoint_url, json=current_netbox)
                    create_response.raise_for_status()
                    
                    time.sleep(retry_delay)
                    
                    # Verify creation
                    verify_response = requests.get(netbox_endpoint_url)
                    verify_response.raise_for_status()
                    if len(verify_response.json()) == 0:
                        raise Exception("Endpoint creation verification failed")
                else:
                    # Handle existing endpoints
                    for endpoint in endpoints:
                        if endpoint['id'] != pk:
                            requests.delete(f'{netbox_endpoint_url}/{endpoint["id"]}')
                        elif endpoint != current_netbox:
                            # Update existing endpoint
                            updated_endpoint = endpoint | current_netbox
                            requests.put(f'{netbox_endpoint_url}/{endpoint["id"]}', json=updated_endpoint)
                
                # Check status
                status_response = requests.get(netbox_status_route)
                status_response.raise_for_status()
                status = 'success'
                break
                
            except requests.exceptions.HTTPError as e:
                logger.error(f'HTTP error on attempt {attempt + 1}: {e}')
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    continue
            except requests.exceptions.RequestException as e:
                logger.error(f'Error on attempt {attempt + 1}: {e}')
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    continue
        
        return status
    
    def proxmox_status(self, pk: int, base_url: str) -> str:
        status = 'error'
        max_retries = 3
        retry_delay = 1
        
        try:
            proxmox_service_obj = ProxmoxEndpoint.objects.get(pk=pk)
        except ProxmoxEndpoint.DoesNotExist:
            logger.error(f"Proxmox endpoint with pk={pk} not found")
            return status
        
        if proxmox_service_obj:
            proxmox_ip_address = str(proxmox_service_obj.ip_address).split('/')[0]
            proxmox_domain = proxmox_service_obj.domain if proxmox_service_obj.domain else None
            
            url = None
            if proxmox_domain:
                url = f'{base_url}/proxmox/version?domain={proxmox_domain}'
            elif proxmox_ip_address:
                url = f'{base_url}/proxmox/version?ip_address={proxmox_ip_address}'
            
            if url:
                for attempt in range(max_retries):
                    try:
                        response = requests.get(url, verify=proxmox_service_obj.verify_ssl)
                        response.raise_for_status()
                        status = 'success'
                        break
                    except requests.exceptions.HTTPError as e:
                        logger.error(f'HTTP error on attempt {attempt + 1}: {e}')
                        if attempt < max_retries - 1:
                            time.sleep(retry_delay)
                            continue
                    except requests.exceptions.RequestException as e:
                        logger.error(f'Error on attempt {attempt + 1}: {e}')
                        if attempt < max_retries - 1:
                            time.sleep(retry_delay)
                            continue
        
        return status

@require_GET
def get_service_status(
    request: HtmxHttpRequest,
    service: str,
    pk: int,
) -> HttpResponse:
    """Get the status of a service."""
    template_name = 'netbox_proxbox/status_badge.html'
    status = 'unknown'
    
    service_status = ServiceStatus()
    
    if service == 'fastapi':
        fastapi_response = service_status.fastapi_status(pk)
        status = 'success' if fastapi_response.get('connected') else 'error'
    else:
        try:
            fastapi_response = service_status.fastapi_status(pk=FastAPIEndpoint.objects.first().id)
        except FastAPIEndpoint.DoesNotExist:
            logger.error("No FastAPI endpoints found")
            pass
    
    if service == 'netbox' and fastapi_response.get('connected'):
        logger.info('Checking NetBox status...')
        netbox_response = service_status.netbox_status(pk=pk, base_url=service_status.connected_url)
        status = netbox_response if netbox_response is not None else 'error'
    
    if service == 'proxmox' and fastapi_response.get('connected'):
        logger.info('Checking Proxmox status...')
        proxmox_response = service_status.proxmox_status(pk=pk, base_url=service_status.connected_url)
        status = proxmox_response if proxmox_response is not None else 'error'
    
    return render(
        request,
        template_name,
        {
            'status': status
        }
    )
 