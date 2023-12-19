from fastapi import APIRouter, Depends

from typing import Annotated, Any

# Import Both Proxmox Sessions and Netbox Session Dependencies
from netbox_proxbox.backend.session.proxmox import ProxmoxSessionsDep
from netbox_proxbox.backend.session.netbox import NetboxSessionDep

from netbox_proxbox.backend.logging import logger

from netbox_proxbox.backend import (
    ClusterType,
    Cluster,
    Site,
    DeviceRole,
    DeviceType,
    Device
)

router = APIRouter()


async def proxmox_session_with_cluster(
    pxs: ProxmoxSessionsDep,
    nb: NetboxSessionDep
):
    """Get Proxmox Session with Cluster"""


@router.get("/")
async def proxbox_get_clusters(
    pxs: ProxmoxSessionsDep,
    nb: NetboxSessionDep
):
    
    
    """Automatically sync Proxmox Clusters with Netbox Clusters"""
    
    result = []
    
    for px in pxs:
        
        """
        Before creating the Cluster, we need to create the Cluster Type.
        """
        cluster_type_name = f"Proxmox {px.mode.capitalize()}"
        cluster_type_slug = f"proxmox-{px.mode}"
        
        
        standalone_description = "Proxmox Standalone. This Proxmox has only one node and thus is not part of a Cluster."
        cluster_description = "Proxmox Cluster. This Proxmox has more than one node and thus is part of a Cluster."
        
        
        description = ""
        if px.mode == "standalone":
            description = standalone_description
        elif px.mode == "cluster":
            description = cluster_description
        
        # Create Cluster Type object before the Cluster itself
        cluster_type_obj = await ClusterType(nb = nb).post(
            data = {
                "name": cluster_type_name,
                "slug": cluster_type_slug,
                "description": description
            }
        )
        
        # Create the Cluster
        cluster_obj = await Cluster(nb = nb).post(
            data = {
                "name": px.name,
                "slug": px.name,
                "type": cluster_type_obj["id"],
                "status": "active",
            }
        )
         
        result.append(
            {
                "name": px.name,
                "netbox": {
                    "cluster": cluster_obj,
                }
            }
        )
    
    return result

@router.get("/nodes")
async def get_nodes(
    #pxs: ProxmoxSessionsDep,
    nb: NetboxSessionDep,
    pxs: ProxmoxSessionsDep,
):
    
    """Get Proxmox Nodes from a Cluster"""

    
    result = []
    
    for px in pxs:
        
        
        get_cluster_from_netbox = await Cluster(nb = nb).get(name = px.name)
    
        # Get Proxmox Nodes from the current Proxmox Cluster
        proxmox_nodes = px.session.nodes.get()
        
        device_role = await DeviceRole(nb = nb).get()
        device_type = await DeviceType(nb = nb).get()
        site = await Site(nb = nb).get()
        
        
        nodes = [
            await Device(nb=nb).post(data = {
                "name": node.get("node"),
                "cluster": px.get("netbox").get("cluster").get("id"),
                "role": device_role.id,
                "site": site.id,
                "status": "active",
                "device_type": device_type.id
                
            }) for node in proxmox_nodes
        ]
        
        
        
        logger.debug(f"Nodes: {nodes}")
    
        
        result.append({
            "cluster_netbox_object": get_cluster_from_netbox,
            "nodes_netbox_object": nodes,
            "cluster_proxmox_object": px.session.nodes.get(),

        })
        
    return result