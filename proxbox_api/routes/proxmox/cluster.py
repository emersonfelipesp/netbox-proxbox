
from fastapi import APIRouter, Query

from typing import Annotated

from proxbox_api.schemas.proxmox import *
from proxbox_api.session.proxmox import ProxmoxSessionsDep
from proxbox_api.enum.proxmox import *

router = APIRouter()


# /proxmox/cluster/ API Endpoints
@router.get("/status")
async def cluster_status(
    pxs: ProxmoxSessionsDep
):
    """
    ### Retrieve the status of clusters from multiple Proxmox sessions.
    
    **Args:**
    - **pxs (`ProxmoxSessionsDep`):** A list of Proxmox session dependencies.
    
    **Returns:**
    - **list:** A list of dictionaries containing the status of each cluster.
    """
    
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
    
    """
    ### Fetches Proxmox cluster resources.
    
    This asynchronous function retrieves resources from a Proxmox cluster. It supports filtering by resource type.
    
    **Args:**
    - **pxs (`ProxmoxSessionsDep`):** Dependency injection for Proxmox sessions.
    - **type (`Annotated[ClusterResourcesType, Query]`):** Optional. The type of Proxmox resource to return. If not provided, all resources are returned.
    
    **Returns:**
    - **list:** A list of dictionaries containing the Proxmox cluster resources.
    """
    
    json_response = []
    
    for px in pxs:
        
        json_response.append(
            {
                px.name: px.session("cluster/resources").get(type = type) if type else px.session("cluster/resources").get()
            }
        )

    return json_response
