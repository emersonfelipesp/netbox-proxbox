
from fastapi import APIRouter, Query, Depends

from typing import Annotated
from pydantic import BaseModel, RootModel
from proxbox_api.schemas.proxmox import *
from proxbox_api.session.proxmox import ProxmoxSessionsDep
from proxbox_api.enum.proxmox import *

router = APIRouter()

class ClusterNodeStatusSchema(BaseModel):
    id: str
    name: str
    type: str
    ip: str | None = None
    level: str | None = None
    local: int | None = None
    nodeid: int | None = None
    online: int | None = None
    
class ClusterStatusSchema(ClusterNodeStatusSchema):
    id: str
    name: str
    type: str
    nodes: int
    quorate: int
    version: int
    node_list: list[ClusterNodeStatusSchema] | None = None
    
ClusterStatusSchemaList = list[ClusterStatusSchema]
    
# /proxmox/cluster/ API Endpoints
@router.get("/status", response_model=ClusterStatusSchemaList)
async def cluster_status(
    pxs: ProxmoxSessionsDep
) -> ClusterStatusSchemaList:
    """
    ### Retrieve the status of clusters from multiple Proxmox sessions.
    
    **Args:**
    - **pxs (`ProxmoxSessionsDep`):** A list of Proxmox session dependencies.
    
    **Returns:**
    - **list (`ClusterStatusSchemaList`):** A list of dictionaries containing the status of each cluster.
    """
    
    async def parse_cluster_status(data: dict) -> ClusterStatusSchema:
        node_list = []
        cluster: ClusterStatusSchema = None
        
        for item in data:
            if item.get('type') == 'cluster':
                cluster = ClusterStatusSchema(**item)
            
            if item.get('type') == 'node':
                node_list.append(ClusterNodeStatusSchema(**item))

        cluster.node_list = node_list
            
        if cluster:
            return cluster
    
    
    return ClusterStatusSchemaList([
        await parse_cluster_status(px.session('cluster/status').get())
        for px in pxs
    ])

ClusterStatusDep = Annotated[ClusterStatusSchemaList, Depends(cluster_status)]

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
