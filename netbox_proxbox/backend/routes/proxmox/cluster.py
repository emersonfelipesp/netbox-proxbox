
from fastapi import APIRouter, Depends, HTTPException, Path, Query

from typing import Annotated

from netbox_proxbox.backend.schemas.proxmox import *
from netbox_proxbox.backend.session.proxmox import ProxmoxSessionsDep
from netbox_proxbox.backend.exception import ProxboxException
from netbox_proxbox.backend.enum.proxmox import *

router = APIRouter()


# /proxmox/cluster/ API Endpoints
@router.get("/status")
async def cluster_status(
    pxs: ProxmoxSessionsDep
):
    json_response = []
    
    for px in pxs:
        json_response.append(
            {
                px.name: px.session("cluster/status").get()
            }
        )
    return json_response


# /proxmox/cluster/ API Endpoints

@router.get("/resources", response_model=ClusterResourcesList)
async def cluster_resources(
    pxs: ProxmoxSessionsDep,
    type: Annotated[
        ClusterResourcesType, 
        Query(
            title="Proxmox Resource Type",
            description="Type of Proxmox resource to return (ex. 'vm' return QEMU Virtual Machines).",
        )
    ] = None,
):
    json_response = []
    
    for px in pxs:
        
        json_response.append(
            {
                px.name: px.session("cluster/resources").get(type = type) if type else px.session("cluster/resources").get()
            }
        )

    return json_response
