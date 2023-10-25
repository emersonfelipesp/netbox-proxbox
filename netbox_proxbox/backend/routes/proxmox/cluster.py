from fastapi import APIRouter, Depends, HTTPException, Path, Query

from typing import Annotated, Any

from netbox_proxbox.backend.schemas.proxmox import *
from netbox_proxbox.backend.routes.proxmox import ProxmoxSessionDep, get_cluster_name
from netbox_proxbox.backend.exception import ProxboxException
from netbox_proxbox.backend.enum.proxmox import *

router = APIRouter()

@router.get("/resources", response_model=ClusterResourcesList)
async def cluster_resources(
    px_sessions: ProxmoxSessionDep,
    type: Annotated[
        ClusterResourcesType, 
        Query(
            title="Proxmox Resource Type",
            description="Type of Proxmox resource to return (ex. 'vm' return QEMU Virtual Machines).",
        )
    ],
    mode: Annotated[
        ProxmoxModeOptions,
        Query(
            title="Proxmox Cluster Mode",
            description="Defines if the API call will be made to a single cluster or to all clusters.",
        )
    ] = "multi"
):
    json_response = {}
    if mode == "multi":
        
        for px in px_sessions:
            
            try:
                print("Testing Resources/Cluster...")
                cluster_name = await get_cluster_name(px)
                print(cluster_name)

                cluster_resources_response = px("cluster/resources").get(type = "vm")
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