import traceback

from fastapi import FastAPI, Request, WebSocket, Depends, Query, Path
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from typing import Annotated

import asyncio

# pynetbox API Imports
from pynetbox_api.ipam.ip_address import IPAddress
from pynetbox_api.dcim.device import Device, DeviceRole, DeviceType
from pynetbox_api.dcim.interface import Interface
from pynetbox_api.dcim.manufacturer import Manufacturer
from pynetbox_api.virtualization.virtual_machine import VirtualMachine
from pynetbox_api.virtualization.cluster import Cluster
from pynetbox_api.virtualization.cluster_type import ClusterType

from pynetbox_api.exceptions import FastAPIException

# Proxbox API Imports
from proxbox_api import ProxboxTag, proxbox_tag
from proxbox_api.exception import ProxboxException

# Proxmox Routes
from proxbox_api.routes.proxmox import router as proxmox_router
from proxbox_api.routes.proxmox.cluster import (
    router as px_cluster_router,
    ClusterResourcesDep
)
from proxbox_api.routes.proxmox.nodes import router as px_nodes_router

# Netbox Routes
from proxbox_api.routes.netbox import router as netbox_router
from proxbox_api.routes.netbox.dcim import router as nb_dcim_router
from proxbox_api.routes.netbox.virtualization import router as nb_virtualization_router

# Proxbox Routes
from proxbox_api.routes.proxbox import router as proxbox_router
from proxbox_api.routes.proxbox.clusters import router as pb_cluster_router

from proxbox_api.schemas import *

# Sessions
from proxbox_api.session.proxmox import ProxmoxSessionsDep
from proxbox_api.session.netbox import NetboxSessionDep


# Proxmox Deps
from proxbox_api.routes.proxmox.nodes import (
    ProxmoxNodeDep,
    ProxmoxNodeInterfacesDep,
    get_node_network
)
from proxbox_api.routes.proxmox.cluster import ClusterStatusDep

"""
CORS ORIGINS
"""

cfg_not_found_msg = "Netbox configuration not found. Using default configuration."

plugin_configuration: dict = {}

uvicorn_host: str = "localhost"
uvicorn_port: int = 8800

netbox_host: str = "localhost"
netbox_port: int = 80


configuration = None
default_config: dict = {}
plugin_configuration: dict = {}
proxbox_cfg: dict = {}  


fastapi_endpoint = f"http://{uvicorn_host}:{uvicorn_port}"
https_fastapi_endpoint = f"https://{uvicorn_host}:{uvicorn_port}"
fastapi_endpoint_port8000 = f"http://{uvicorn_host}:8000"
fastapi_endpoint_port80 = f"http://{uvicorn_host}:80"

netbox_endpoint_port80 = f"http://{netbox_host}:80"
netbox_endpoint_port8000 = f"http://{netbox_host}:8000"
netbox_endpoint = f"http://{netbox_host}:{netbox_port}"
https_netbox_endpoint = f"https://{netbox_host}"
https_netbox_endpoint443 = f"https://{netbox_host}:443"
https_netbox_endpoint_port = f"https://{netbox_host}:{netbox_port}"


PROXBOX_PLUGIN_NAME: str = "netbox_proxbox"


# Init FastAPI
app = FastAPI(
    title="Proxbox Backend",
    description="## Proxbox Backend made in FastAPI framework",
    version="0.0.1"
)

@app.on_event('startup')
def on_startup():
    from proxbox_api.database import create_db_and_tables
    create_db_and_tables()

"""
CORS Middleware
"""

origins = [
    fastapi_endpoint,
    fastapi_endpoint_port8000,
    fastapi_endpoint_port80,
    https_fastapi_endpoint,
    netbox_endpoint,
    netbox_endpoint_port80,
    netbox_endpoint_port8000,
    https_netbox_endpoint,
    https_netbox_endpoint443,
    https_netbox_endpoint_port,
    "http://localhost",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"]
)


@app.exception_handler(ProxboxException)
async def proxmoxer_exception_handler(request: Request, exc: ProxboxException):
    return JSONResponse(
        status_code=400,
        content={
            "message": exc.message,
            "detail": exc.detail,
            "python_exception": exc.python_exception,
        }
    )

from proxbox_api.routes.proxbox.clusters import get_nodes, get_virtual_machines

         
@app.get('/dcim/devices')
async def create_devices():
    return {
        "message": "Devices created"
    }


@app.get(
    '/dcim/devices/create',
    response_model=Device.SchemaList,
    response_model_exclude_none=True,
    response_model_exclude_unset=True,
)
async def create_proxmox_devices(
    clusters_status: ClusterStatusDep,
    nb: NetboxSessionDep,
    node: str | None = None,
):
    device_list: list = []
    
    '''
    cluster_type_standalone = ClusterType(
        name='Standalone',
        slug='standalone',
        description='Proxmox standalone cluster (single-node).',
        tags=[ProxboxTag(bootstrap_placeholder=True).id]
    )
    
    cluster_type_cluster = ClusterType(
        name='Cluster',
        slug='cluster',
        description='Proxmox cluster mode (multiple-nodes).',
        tags=[ProxboxTag(bootstrap_placeholder=True).id]
    )
    
    cluster_type_mapping: dict = {
        'standalone': cluster_type_standalone,
        'cluster': cluster_type_cluster
    }
    '''
    
    for cluster_status in clusters_status:
        '''
        print(f'cluster_status: {cluster_status}')
        # Get cluster type, if not found, use bootstrap placeholder.
        cluster_type: ClusterType = cluster_type_mapping.get(cluster_status.mode, ClusterType(bootstrap_placeholder=True).result)
        print(f'cluster_type: {cluster_type}')
        cluster_type_id = int(getattr(cluster_type, 'id', cluster_type.get('id')))
        print(cluster_type_id)
        
        
        cluster = Cluster(
            name = cluster_status.name,
            type = cluster_type_id,
            status = 'active',
            description = f'Proxmox {cluster_status.mode} cluster.',
            tags=[ProxboxTag(bootstrap_placeholder=True).id]
        ).id
        
        print('\n\ncluster:', cluster)
        '''
        #cluster_id = getattr(cluster, 'id', cluster.get('id', None))
        
        for node_obj in cluster_status.node_list:
            try:
                # TODO: Based on name.ip create Device IP Address
                netbox_device = Device(
                    nb=nb.session,
                    name=node_obj.name,
                    tags=[ProxboxTag(bootstrap_placeholder=True).id],
                    cluster = Cluster(
                        name = cluster_status.name,
                        type = ClusterType(
                            name=cluster_status.mode.capitalize(),
                            slug=cluster_status.mode,
                            description=f'Proxmox {cluster_status.mode} mode',
                            tags=[ProxboxTag(bootstrap_placeholder=True).id]
                        )['id'],
                        status = 'active',
                        description = f'Proxmox {cluster_status.mode} cluster.',
                        tags=[ProxboxTag(bootstrap_placeholder=True).id]
                    ).get('id', Cluster(bootstrap_placeholder=True).id),
                )
                
                # If node, return only the node requested.
                if node:
                    if node == node_obj.name:
                        return Device.SchemaList([netbox_device])
                    else:
                        continue
                    
                # If not node, return all nodes.
                elif not node:
                    device_list.append(netbox_device)

            except FastAPIException as error:
                traceback.print_exc()
                raise ProxboxException(
                    message="Unknown Error creating device in Netbox",
                    detail=f"Error: {str(error)}"
                )
            
            except Exception as error:
                traceback.print_exc()
                raise ProxboxException(
                    message="Unknown Error creating device in Netbox",
                    detail=f"Error: {str(error)}"
                )
    return Device.SchemaList(device_list)

ProxmoxCreateDevicesDep = Annotated[Device.SchemaList, Depends(create_proxmox_devices)]

async def create_interface_and_ip(node_interface, node):
    interface_type_mapping: dict = {
        'lo': 'loopback',
        'bridge': 'bridge',
        'bond': 'lag',
        'vlan': 'virtual',
    }
        
    node_cidr = getattr(node_interface, 'cidr', None)
    
    interface = Interface(
        device=node.id,
        name=node_interface.iface,
        status='active',
        type=interface_type_mapping.get(node_interface.type, 'other'),
        tags=[ProxboxTag(bootstrap_placeholder=True).id],
    )
    
    try:
        interface_id = getattr(interface, 'id', interface.get('id', None))
    except:
        interface_id = None
        pass

    if node_cidr and interface_id:
        IPAddress(
            address=node_cidr,
            assigned_object_type='dcim.interface',
            assigned_object_id=int(interface_id),
            status='active',
            tags=[ProxboxTag(bootstrap_placeholder=True).id],
        )
    
    return interface

@app.get(
    '/dcim/devices/{node}/interfaces/create',
    response_model=Interface.SchemaList,
    response_model_exclude_none=True,
    response_model_exclude_unset=True
)
async def create_proxmox_device_interfaces(
    nodes: ProxmoxCreateDevicesDep,
    node_interfaces: ProxmoxNodeInterfacesDep,
):
    node = None
    for device in nodes:
        node = device[1][0]
        break

    return InterfaceSchemaList(
        await asyncio.gather(
            *[create_interface_and_ip(node_interface, node) for node_interface in node_interfaces]
        )
    )

ProxmoxCreateDeviceInterfacesDep = Annotated[Interface.SchemaList, Depends(create_proxmox_device_interfaces)]  

@app.get('/dcim/devices/interfaces/create')
async def create_all_devices_interfaces(
    #nodes: ProxmoxCreateDevicesDep,
    #node_interfaces: ProxmoxNodeInterfacesDep,
):  
    return {
        'message': 'Endpoint currently not working. Use /dcim/devices/{node}/interfaces/create instead.'
    }
    
    nodes = nodes.root
    for node in nodes:
        print(node.name)

    return await asyncio.gather(*[create_proxmox_device_interfaces(
        node=node.name,
        nodes=nodes,
        node_interfaces=node_interfaces
    ) for node in nodes])

@app.get('/virtualization/cluster-types/create')
async def create_cluster_types():
    # TODO
    pass


@app.get('/virtualization/clusters/create')
async def create_clusters(cluster_status: ClusterStatusDep):
    pass

'''
@app.get('/virtualization/virtual-machines/create')
async def create_virtual_machines(
    cluster_resources: ClusterResourcesDep
):

    TODO: Add previus fields (located at: /proxbox_api/routes/proxbox/clusters/__init__.py)
    "role": getattr(role, "id", None),
    "custom_fields": {
        "proxmox_vm_id": vm.get('vmid'),
        "proxmox_start_at_boot": start_at_boot,
        "proxmox_unprivileged_container": unprivileged_container,
        "proxmox_qemu_agent": qemu_agent,
        "proxmox_search_domain": search_domain,
    },
    "platform": platform
    
    async def _create_vm(cluster: dict):
        for cluster_name, resources in cluster.items():
            return await asyncio.gather(*[
                VirtualMachine(
                        name=resource.get('name'),
                        status=VirtualMachine.status_field.get(resource.get('status'), 'active'),
                        cluster=Cluster(name=cluster_name).get('id'),
                        device=Device(name=resource.get('node')).get('id'),
                        vcpus=int(resource.get("maxcpu", 0)),
                        memory=int(resource.get("mexmem", 0)),
                        disk=int(int(resource.get("maxdisk", 0)) / 1000000),
                        tags=[ProxboxTag(bootstrap_placeholder=True).id]
                    ) for resource in resources if resource.get('type') in ('qemu' or 'lxc')
                ])
        
    return await asyncio.gather(*[_create_vm(cluster) for cluster in cluster_resources])
'''

@app.get('/virtualization/virtual-machines/create')
async def create_virtual_machines(
    cluster_resources: ClusterResourcesDep
):
    async def _create_vm(cluster: dict):
        tasks = []  # Collect coroutines
        for cluster_name, resources in cluster.items():
            for resource in resources:
                if resource.get('type') in ('qemu', 'lxc'):
                    tasks.append(create_vm_task(cluster_name, resource))

        return await asyncio.gather(*tasks)  # Gather coroutines

    async def create_vm_task(cluster_name, resource):
        vm_role_mapping: dict = {
            'qemu': {
                'name': 'Virtual Machine (QEMU)',
                'slug': 'virtual-machine-qemu',
                'color': '00ffff',
                'description': 'Proxmox Virtual Machine',
                'tags': [proxbox_tag.id],
                'vm_role': True
            },
            'lxc': {
                'name': 'Container (LXC)',
                'slug': 'container-lxc',
                'color': '7fffd4',
                'description': 'Proxmox LXC Container',
                'tags': [proxbox_tag.id],
                'vm_role': True
            },
            'undefined': {
                'name': 'Unknown',
                'slug': 'unknown',
                'color': '000000',
                'description': 'VM Type not found. Neither QEMU nor LXC.',
                'tags': [proxbox_tag.id],
                'vm_role': True
            }
        }
        
        vm_type = resource.get('type', 'unknown')
        
        
        # Lamba is necessary to treat the object instantiation as a coroutine/function.
        return await asyncio.to_thread(lambda: VirtualMachine(
            name=resource.get('name'),
            status=VirtualMachine.status_field.get(resource.get('status'), 'active'),
            cluster=Cluster(name=cluster_name).get('id'),
            device=Device(name=resource.get('node')).get('id'),
            vcpus=int(resource.get("maxcpu", 0)),
            memory=int(resource.get("maxmem")) // 1000,  # Fixed typo 'mexmem'
            disk=int(resource.get("maxdisk", 0)) // 1000000,
            tags=[ProxboxTag(bootstrap_placeholder=True).id],
            role=DeviceRole(**vm_role_mapping.get(vm_type)).get('id', None),
        ))

    return await asyncio.gather(*[_create_vm(cluster) for cluster in cluster_resources])

                
                
                
 
@app.get('/virtualization/virtual-machines/interfaces/create')
async def create_virtual_machines_interfaces():
    # TODO
    pass

@app.get('/virtualization/virtual-machines/interfaces/ip-address/create')
async def create_virtual_machines_interfaces_ip_address():
    # TODO
    pass

@app.get('/virtualization/virtual-machines/virtual-disks/create')
async def create_virtual_disks():
    # TODO
    pass




''' 
@app.get(
    '/dcim/devices/{node}/interfaces/ip-address/create',
    response_model=InterfaceSchemaList,
    response_model_exclude_none=True,
    response_model_exclude_unset=True
)
async def create_proxmox_interface_ip_address(
    nb: NetboxSessionDep,
    nodes: ProxmoxCreateDeviceInterfacesDep,
    node_interfaces: ProxmoxNodeInterfacesDep
):
'''
#
# Routes (Endpoints)
#

# Netbox Routes
app.include_router(netbox_router, prefix="/netbox", tags=["netbox"])
#app.include_router(nb_dcim_router, prefix="/netbox/dcim", tags=["netbox / dcim"])
#app.include_router(nb_virtualization_router, prefix="/netbox/virtualization", tags=["netbox / virtualization"])

# Proxmox Routes
app.include_router(px_nodes_router, prefix="/proxmox/nodes", tags=["proxmox / nodes"])
app.include_router(px_cluster_router, prefix="/proxmox/cluster", tags=["proxmox / cluster"])
app.include_router(proxmox_router, prefix="/proxmox", tags=["proxmox"])

# Proxbox Routes
app.include_router(proxbox_router, prefix="/proxbox", tags=["proxbox"])
app.include_router(pb_cluster_router, prefix="/proxbox/clusters", tags=["proxbox / clusters"])






@app.get("/")
async def standalone_info():
    return {
        "message": "Proxbox Backend made in FastAPI framework",
        "proxbox": {
            "github": "https://github.com/netdevopsbr/netbox-proxbox",
            "docs": "https://docs.netbox.dev.br",
        },
        "fastapi": {
            "github": "https://github.com/tiangolo/fastapi",
            "website": "https://fastapi.tiangolo.com/",
            "reason": "FastAPI was chosen because of performance and reliabilty."
        }
    }

'''
@app.websocket("/ws")
async def websocket_endpoint(
    nb: NetboxSessionDep,
    pxs: ProxmoxSessionsDep,
    websocket: WebSocket
):
    try:
        await websocket.accept()
    except Exception as error:
        print(f"Error while accepting WebSocket connection: {error}")
        await websocket.close()
    
    data = None

    while True:
        try:
            data = await websocket.receive_text()
        except Exception as error:
            print(f"Error while receiving data from WebSocket: {error}")
            await websocket.close()
            break
        
        if data == "Start":
            await get_nodes(nb=nb, pxs=pxs, websocket=websocket)
            await get_virtual_machines(nb=nb, pxs=pxs, websocket=websocket)
            await websocket.close()
            
        if data == "Sync Nodes":
            await get_nodes(nb=nb, pxs=pxs, websocket=websocket)
            await websocket.close()

        if data == "Sync Virtual Machines":
            await get_virtual_machines(nb=nb, pxs=pxs, websocket=websocket)
            await websocket.close()
            
        else:
            print("Invalid command.")
            await websocket.send_text("Invalid command.")
            await websocket.close()

        await websocket.close()
'''
    
'''
@app.websocket("/ws/virtual-machine")
async def websocket_vm_endpoint(
    nb: NetboxSessionDep,
    pxs: ProxmoxSessionsDep,
    websocket: WebSocket
):
    try:
        await websocket.accept()
    except Exception as error:
        print(f"Error while accepting WebSocket connection: {error}")
        await websocket.close()

    data = None

    while True:
        try:
            data = await websocket.receive_text()
        except Exception as error:
            print(f"Error while receiving data from WebSocket: {error}")
            await websocket.close()
            break

        if data == "Sync Virtual Machines":
            await get_virtual_machines(nb=nb, pxs=pxs, websocket=websocket)
            await websocket.close()

        else:
            print("Invalid command.")
            await websocket.send_text("Invalid command.")
            await websocket.close()
'''