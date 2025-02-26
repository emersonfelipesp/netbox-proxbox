
from fastapi import APIRouter, Query, Depends

from typing import Annotated
from pydantic import BaseModel, RootModel
from proxbox_api.schemas.proxmox import *
from proxbox_api.session.proxmox import ProxmoxSessionsDep
from proxbox_api.enum.proxmox import *
from proxbox_api.session.proxmox import ProxmoxSession

router = APIRouter()

class BaseClusterStatusSchema(BaseModel):
    id: str
    name: str
    type: str

class ClusterNodeStatusSchema(BaseClusterStatusSchema):
    ip: str
    level: str | None = None
    local: int
    nodeid: int
    online: int
    
class ClusterStatusSchema(BaseClusterStatusSchema):
    nodes: int
    quorate: int
    version: int
    mode: str
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
    
    ### Example Response:
    ```json
    [
        'id': 'cluster',
        'name': 'Cluster-Name',
        'type': 'cluster',
        'mode': 'standalone',
        'nodes:' 2,
        'quorate': 1,
        'version': 1,
        'node_list': [
            {
                'id': 'node/node-name',
                'name': 'node-name',
                'type': 'node',
                'ip': '10.0.0.1',
                'level: '',
                'local': 1,
                'nodeid': 1,
                'online': 1                
            },
            {
                'id': 'node/node-name2',
                'name': 'node-name2',
                'type': 'node',
                'ip': '10.0.0.2',
                'level: '',
                'local': 1,
                'nodeid': 1,
                'online': 1                
            }
        ]
    ]
    ```
    """
    async def parse_cluster_status(proxmox_object: ProxmoxSession, data: dict) -> ClusterStatusSchema:
        node_list = []
        cluster: ClusterStatusSchema = None
        
        for item in data:
            item['mode'] = proxmox_object.mode
            if item.get('type') == 'cluster':
                cluster = ClusterStatusSchema(**item)
            
            if item.get('type') == 'node':
                node_list.append(ClusterNodeStatusSchema(**item))

        cluster.node_list = node_list
            
        if cluster:
            return cluster
    
    
    return ClusterStatusSchemaList([
        await parse_cluster_status(
            proxmox_object=px,
            data=px.session('cluster/status').get())
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

ClusterResourcesDep = Annotated[ClusterResourcesList, Depends(cluster_resources)]