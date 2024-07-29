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
        
        
        
            role = await DeviceRole(nb = nb).get(slug = vm.get("type"))
            if role == None:
            
                vm_type = vm.get("type")
                
                vm_name = None
                
                color = "000000"
                
                if vm_type == "qemu":
                    vm_name = "Virtual Machine (QEMU)"
                    color = "00ffff"
                    description = "Proxmox Virtual Machine"

                if vm_type == "lxc":
                    vm_name = "Container (LXC)"
                    color = "7fffd4"
                    description = "Proxmox Container"
                
                role = await DeviceRole(nb = nb).post(data = {
                    "name": vm_name,
                    "slug": vm_type,
                    "vm_role": True,
                    "color": color,
                    "description": description
                })
                
            try:
                custom_field_id = nb.session.extras.custom_fields.get(name="proxmox_vm_id")
            except:
                custom_field_id = nb.session.extras.custom_fields.create(
                    {
                        "object_types": [
                            "virtualization.virtualmachine"
                        ],
                        "type": "integer",
                        "name": "proxmox_vm_id",
                        "label": "Proxmox VM ID",
                        "description": "Proxmox Virtual Machine or Container ID",
                        "ui_visible": "always",
                        "ui_editable": "hidden",
                        "weight": 100,
                        "filter_logic": "loose",
                        "search_weight": 1000,
                    }
                )
            print(f'custom_field_id: {custom_field_id}')
            
            
            platform = None
            
            #if vm.get("type") == 'lxc': print(px.session.nodes.get(f'nodes/{vm.get("node")}/lxc/{vm.get("vmid")}/config')
            if vm.get("type") == 'lxc': 
                vm_config = px.session.nodes(vm.get("node")).lxc(vm.get("vmid")).config.get()
                
                platform_name = vm_config.get("ostype").capitalize()
                platform_slug = vm_config.get("ostype")
                
                platform = nb.session.dcim.platforms.get(name = platform_name).id
                if not platform:
                    platform = nb.session.dcim.platforms.create(
                        name = platform_name,
                        slug = platform_slug
                    ).id

                    
            if vm.get("type") == 'qemu': vm_config = px.session.nodes(vm.get("node")).qemu(vm.get("vmid")).config.get()
            
            
            print(f"vm_config: {vm_config}")
            
            print(f"\nplatform: {platform}\n")
            
            # Create Custom Field and add Virtual Machine Proxmox ID
            new_virtual_machine =  await VirtualMachine(nb = nb).post(data = {
                    "name": vm.get("name"),
                    "cluster": cluster.id,
                    "device": device,
                    "status": VirtualMachineStatus(vm.get("status")).name,
                    "vcpus": int(vm.get("maxcpu", 0)),
                    "memory": int(vm_config.get("memory")),
                    "disk": int(int(vm.get("maxdisk", 0)) / 1000000000),
                    "role": role.id,
                    "custom_fields": {
                        "proxmox_vm_id": vm.get("vmid")
                    },
                    "platform": platform
                }
            )
            

            

            
            created_virtual_machines.append(new_virtual_machine)
            print(f"new_virtual_machine: {new_virtual_machine} | {type(new_virtual_machine)}")
            

            

            
            
        result.append({
            "name": px.name,
            "netbox": {
                "virtual_machines": created_virtual_machines
            }
        })
    
    print("CACHE end:", cache.cache)
    return result