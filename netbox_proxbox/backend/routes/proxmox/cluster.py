
from fastapi import APIRouter, Depends, HTTPException, Path, Query
"""
from typing import Annotated

from netbox_proxbox.backend.schemas.proxmox import *
from netbox_proxbox.backend.routes.proxmox import ProxmoxSessionsDep
from netbox_proxbox.backend.exception import ProxboxException
from netbox_proxbox.backend.enum.proxmox import *
"""
router = APIRouter()
"""
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
    mode: Annotated[
        ProxmoxModeOptions,
        Query(
            title="Proxmox Cluster Mode",
            description="Defines if the API call will be made to a single cluster or to all clusters.",
        )
    ] = "multi"
):
    pxs = await pxs.sessions()
    json_response = {}
    
    print(pxs)
    if mode == "multi":
        
        for px in pxs:
            
            try:
                cluster_name = px.get("cluster_name")
                print(cluster_name)

                cluster_resources_response = px[session]("cluster/resources").get(type = type) if type else px("cluster/resources").get()
                json_response[cluster_name] = cluster_resources_response
 
            except Exception as error:
                raise ProxboxException(
                    message = f"Could not validate data returned by Proxmox API (path: cluster/resources)",
                    python_exception = f"{error}"
                )
                
    if mode == "single":
        raise HTTPException(
                status_code=501,
                detail="Single-cluster API call not implemented yet."
            )

    return json_response
"""