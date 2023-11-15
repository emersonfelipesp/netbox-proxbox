from fastapi import APIRouter, Depends, HTTPException, Path, Query

from typing import Annotated, Any, List

from proxmoxer.core import ResourceException

from netbox_proxbox.backend.schemas.proxmox import *
from netbox_proxbox.backend.session.proxmox import ProxmoxSessionsDep
from netbox_proxbox.backend.exception import ProxboxException
from netbox_proxbox.backend.enum.proxmox import *

router = APIRouter()

#
# /proxmox/* API Endpoints
#

@router.get("/sessions")
async def proxmox_sessions(
    pxs: ProxmoxSessionsDep
):
    json_response = []
    
    for px in pxs:
        json_response.append(
            {
                "domain": px.domain,
                "http_port": px.http_port,
                "user": px.user,
                "name": px.name,
                "mode": px.mode,
            }
        )
    
    return json_response



@router.get("/version", )
async def proxmox_version(
    pxs: ProxmoxSessionsDep
):
    json_response = []
    
    for px in pxs:
        json_response.append(
            {
                px.name: px.session.version.get()
            }
        )
            
    return json_response


@router.get("/{top_level}")
async def top_level_endpoint(
    pxs: ProxmoxSessionsDep,
    top_level: ProxmoxUpperPaths,
):
    json_response = []
    
    for px in pxs:
        json_response.append(
            {  
                px.name: px.session(top_level).get()
            }
        )
    
    return json_response


@router.get("/")
async def proxmox(
    pxs: ProxmoxSessionsDep
):
    json_response = []
    
    def minimize_result(endpoint_name):
        endpoint_list = []
        result = px.session(endpoint_name).get()
        
        match endpoint_name:
            case "access":
                for obj in result:
                    endpoint_list.append(obj.get("subdir"))
            
            case "cluster":
                for obj in result:
                    endpoint_list.append(obj.get("name"))
                
        return endpoint_list
    
    for px in pxs:  
        json_response.append(
            {
                f"{px.name}": {
                    "access": minimize_result("access"),
                    "cluster": minimize_result("cluster"),
                    "nodes": px.session.nodes.get(),
                    "pools": px.session.pools.get(),
                    "storage": px.session.storage.get(),
                    "version": px.session.version.get(),
                }
            } 
        )

    return {
        "message": "Proxmox API",
        "proxmox_api_viewer": "https://pve.proxmox.com/pve-docs/api-viewer/",
        "github": {
            "netbox": "https://github.com/netbox-community/netbox",
            "pynetbox": "https://github.com/netbox-community/pynetbox",
            "proxmoxer": "https://github.com/proxmoxer/proxmoxer",
            "proxbox": "https://github.com/netdevopsbr/netbox-proxbox"
        },
        "clusters": json_response
    }