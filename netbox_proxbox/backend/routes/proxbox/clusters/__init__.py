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

# from netbox_proxbox.backend.routes.netbox.virtualization.cluster_type import ClusterType
# from netbox_proxbox.backend.routes.netbox.virtualization.cluster import Cluster

# from netbox_proxbox.backend.routes.netbox.dcim.sites import Site
# from netbox_proxbox.backend.routes.netbox.dcim.device_roles import DeviceRole
# from netbox_proxbox.backend.routes.netbox.dcim.device_types import DeviceType
# from netbox_proxbox.backend.routes.netbox.dcim.devices import Device


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
        
        # Create Cluster Type object before the Cluster itself
        cluster_type_obj = await ClusterType(nb = nb).post(
            data = {
                "name": cluster_type_name,
                "slug": cluster_type_slug,
                "description": f"Proxmox Cluster '{px.name}'"
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
        
        print(px.cluster_status)
        
        result.append(cluster_obj)
    
    return result

@router.get("/nodes")
async def get_nodes(
    pxs: ProxmoxSessionsDep,
    nb: NetboxSessionDep,
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
                "cluster": get_cluster_from_netbox["id"],
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