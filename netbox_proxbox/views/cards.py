from django.views import View
from django.shortcuts import render

from netbox_proxbox.models import FastAPIEndpoint, ProxmoxEndpoint
from netbox_proxbox.utils import get_fastapi_url

from django.views.decorators.http import require_GET

from django.http import HttpRequest, HttpResponse
from django_htmx.middleware import HtmxDetails
class HtmxHttpRequest(HttpRequest):
    htmx: HtmxDetails

import requests

@require_GET
def get_proxmox_card(
    request: HtmxHttpRequest,
    pk: int,
) -> HttpResponse:
    template_name = 'netbox_proxbox/home/proxmox_card.html'
    
    fastapi_info = None
    fastapi_url = None
    try:
        fastapi_object = FastAPIEndpoint.objects.first()
        fastapi_info = get_fastapi_url(fastapi_object)
        if fastapi_info is not None:
            fastapi_url = fastapi_info.get('http_url')
    except FastAPIEndpoint.DoesNotExist:
        pass
    
    proxmox_object = None
    try:
        proxmox_object = ProxmoxEndpoint.objects.get(pk=pk)
    except ProxmoxEndpoint.DoesNotExist:
        pass
        
    version_data: list = []
    cluster_data: list = []
    
    if fastapi_url and fastapi_info and proxmox_object:
        domain = str(proxmox_object.ip_address).split('/')[0]
        
        version_endpoint = f'{fastapi_url}/proxmox/version?&domain={domain}'
        print('version_endpoint:', version_endpoint)
        cluster_endpoint = f'{fastapi_url}/proxmox/sessions?domain={domain}'
        
        try:
            version_response = requests.get(version_endpoint)
            cluster_response = requests.get(cluster_endpoint)
            
            version_response.raise_for_status()
            cluster_response.raise_for_status()
            
            version_data = version_response.json()
            print('version-data:', version_data)
            cluster_data = cluster_response.json()
            print('cluster-data:', cluster_data)
        except Exception as error:
            print('HTTP Error ocurred:', error)
            pass
    
    '''
    version_data example:
    [
        {
            "CLUSTER-NAME": {
                "version": "8.3.0",
                "release": "8.3",
                "repoid": "c1689ccb1065a83b"
            }
        }
    ]
    
    cluster_endpoint example:
    [
        {
            "domain": "10.0.0.1",
            "http_port": 8006,
            "user": "root@pam",
            "name": "CLUSTER-NAME",
            "mode": "cluster"
        }
    ]
    '''
    
    # Extract the version and cluster data from the JSON response
    for version, cluster in zip(version_data, cluster_data):
        print(version, cluster)
        for key, value in version.items():
            version_data = value

        cluster_data = cluster
    
    # Combine the version and cluster data into one dictionary
    print(cluster_data, version_data)
    all_data: dict = {}
    if type(cluster_data) is dict and type(version_data) is dict:
        all_data = cluster_data | version_data
    
    return render(
        request,
        template_name,
        {
            'cluster_data': all_data,
            'object': proxmox_object,
        }
    )