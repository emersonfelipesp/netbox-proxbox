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
    Device,
    VirtualMachine
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
    nb: NetboxSessionDep,
    pxs: ProxmoxSessionsDep,
):
    
    """Get Proxmox Nodes from a Cluster"""

    
    result = []
    
    for px in pxs:
        
        # Get Cluster from Netbox based on Proxmox Cluster Name
        get_cluster_from_netbox = await Cluster(nb = nb).get(name = px.name)
    
        # Get Proxmox Nodes from the current Proxmox Cluster
        proxmox_nodes = px.session.nodes.get()
        
        # List Comprehension to create the Nodes in Netbox
        nodes = [
            await Device(nb=nb).post(data = {
                "name": node.get("node"),
                "cluster": get_cluster_from_netbox.id,
                "status": "active",
            }) for node in proxmox_nodes
        ]
        
        logger.debug(f"Nodes: {nodes}")
    
        
        result.append({
            "name": px.name,
            "netbox": {
                "nodes": nodes
            }
        })
        
    return result

@router.get("/nodes/interfaces")
async def get_nodes_interfaces():
    pass

@router.get("/virtual-machines")
async def get_virtual_machines(
    nb: NetboxSessionDep,
    pxs: ProxmoxSessionsDep,
):
    from enum import Enum
    class VirtualMachineStatus(Enum):
        """
        Key are Netbox Status.
        Values are Proxmox Status.
        """
        active = "running"
        offline = "stopped"
    
    result = []
    
    
    containers = []
    
    from netbox_proxbox.backend.cache import cache
    
    print("CACHE start:", cache.cache)
    
    for px in pxs:
        virtual_machines = px.session.cluster.resources.get(type="vm")
        
        created_virtual_machines = []
        
        
        devices = {}
        clusters = {}
        for vm in virtual_machines:
            
            print(f"\n[VM] {vm}\n")
            
            vm_node: str = vm.get("node")
            print(f"vm_node: {vm_node} | {type(vm_node)}")
            
            """
            Get Device from Netbox based on Proxmox Node Name only if it's not already in the devices dict
            This way we are able to minimize the number of requests to Netbox API
            """
            if devices.get(vm_node) == None:
                devices[vm_node] = await Device(nb = nb).get(name = vm.get("node"))
                
            device = devices[vm_node]
            print(f"devices[vm_node]: {devices[vm_node]} | {device}")
            print(f"DEVICE TEST: {device}")
            
            
            """
            Get Cluster from Netbox based on Cluster Name only if it's not already in the devices dict
            This way we are able to minimize the number of requests to Netbox API
            """
            if clusters.get(px.name) == None:
                clusters[px.name] = await Cluster(nb = nb).get(name = px.name)
            
            cluster = clusters[px.name]
        
            created_virtual_machines.append(
                await VirtualMachine(nb = nb).post(data = {
                    "name": vm.get("name"),
                    "cluster": cluster.id,
                    "device": device,
                    "status": VirtualMachineStatus(vm.get("status")).name,
                    "vcpus": int(vm.get("maxcpu", 0)),
                    "memory": int(int(vm.get("maxmem", 0)) / 1000000),
                    "disk": int(int(vm.get("maxdisk", 0)) / 1000000000),
                })
            )
        
        result.append({
            "name": px.name,
            "netbox": {
                "virtual_machines": created_virtual_machines
            }
        })
    
    print("CACHE end:", cache.cache)
    return result