from fastapi import APIRouter, Depends

from typing import Annotated, Any

# Import Both Proxmox Sessions and Netbox Session Dependencies
from netbox_proxbox.backend.session.proxmox import ProxmoxSessionsDep
from netbox_proxbox.backend.session.netbox import NetboxSessionDep


from netbox_proxbox.backend.routes.netbox.virtualization.cluster_type import ClusterType
from netbox_proxbox.backend.routes.netbox.virtualization.cluster import Cluster

router = APIRouter()

@router.get("/")
async def proxbox_get_clusters(
    pxs: ProxmoxSessionsDep,
    nb: NetboxSessionDep
):
    
    
    """Automatically sync Proxmox Clusters with Netbox Clusters"""
    
    result = []
    
    for px in pxs:
        
        cluster_type_name = f"Proxmox {px.mode.capitalize()}"
        cluster_type_slug = f"proxmox-{px.mode}"
        
        cluster_type_obj = await ClusterType(nb = nb).post(
            data = {
                "name": cluster_type_name,
                "slug": cluster_type_slug,
                "description": f"Proxmox Cluster '{px.name}'"
            }
        )
        
        cluster_obj = await Cluster(nb = nb).post(
            data = {
                "name": px.name,
                "slug": px.name,
                "type": cluster_type_obj["id"],
                "status": "active",
            }
        )
        
        result.append(cluster_obj)
    
    return result
        