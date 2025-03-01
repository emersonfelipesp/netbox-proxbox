import traceback

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, Depends, Query, Path
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from proxmoxer.core import ResourceException

import re
from pydantic import BaseModel, Field, conint, constr, model_validator, root_validator, Extra
from typing import Annotated, Optional, Dict, Any

import asyncio

# pynetbox API Imports
from pynetbox_api.ipam.ip_address import IPAddress
from pynetbox_api.dcim.device import Device, DeviceRole, DeviceType
from pynetbox_api.dcim.interface import Interface
from pynetbox_api.dcim.manufacturer import Manufacturer
from pynetbox_api.dcim.site import Site
from pynetbox_api.virtualization.virtual_machine import VirtualMachine
from pynetbox_api.virtualization.interface import VMInterface
from pynetbox_api.virtualization.cluster import Cluster
from pynetbox_api.virtualization.cluster_type import ClusterType
from pynetbox_api.extras.custom_field import CustomField
from pynetbox_api.extras.tag import Tags
from pynetbox_api.exceptions import FastAPIException

# Proxbox API Imports
from proxbox_api.exception import ProxboxException
from pydantic import BaseModel


async def proxbox_tag():
    return await asyncio.to_thread(
        lambda: Tags(
            name='Proxbox',
            slug='proxbox',
            color='ff5722',
            description='Proxbox Identifier (used to identify the items the plugin created)'
        )
    )
    
ProxboxTagDep = Annotated[Tags.Schema, Depends(proxbox_tag)]

# Proxmox Routes
from proxbox_api.routes.proxmox import router as proxmox_router
from proxbox_api.routes.proxmox.cluster import (
    router as px_cluster_router,
    ClusterResourcesDep
)
from proxbox_api.routes.proxmox.nodes import router as px_nodes_router

# Netbox Routes
from proxbox_api.routes.netbox import router as netbox_router, GetNetBoxEndpoint
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

netbox_url: str = "http://localhost:80"
    

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

'''
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
'''

PROXBOX_PLUGIN_NAME: str = "netbox_proxbox"


# Init FastAPI
app = FastAPI(
    title="Proxbox Backend",
    description="## Proxbox Backend made in FastAPI framework",
    version="0.0.1"
)


"""
CORS Middleware
"""

    
origins = [
    netbox_url,
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

sync_status_html = "<span class='text-bg-yellow badge p-1' title='Syncing VM' ><i class='mdi mdi-sync'></i></span>"
completed_sync_html = "<span class='text-bg-green badge p-1' title='Synced VM'><i class='mdi mdi-check'></i></span>"
        
@app.get('/cache')
async def get_cache():
    from pynetbox_api.cache import global_cache
    return global_cache.return_cache()
 
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
    tag: ProxboxTagDep,
    node: str | None = None,
    websocket = WebSocket
):
    device_list: list = []
    
    for cluster_status in clusters_status:
        for node_obj in cluster_status.node_list:
            websocket_node_json: dict = {}
            await websocket.send_json(
                {
                    'object': 'device',
                    'type': 'create',
                    'data': {
                        'completed': False,
                        'sync_status': sync_status_html,
                        'rowid': node_obj.name,
                        'name': node_obj.name,
                        'netbox_id': None,
                        'manufacturer': None,
                        'role': None,
                        'cluster': cluster_status.mode.capitalize(),
                        'device_type': None,
                    }
                }
            )
            
            
            try:
                cluster_type = await asyncio.to_thread(lambda: ClusterType(
                    name=cluster_status.mode.capitalize(),
                    slug=cluster_status.mode,
                    description=f'Proxmox {cluster_status.mode} mode',
                    tags=[tag.get('id', None)]
                ))
                
                #cluster_type = await asyncio.to_thread(lambda: )
                cluster = await asyncio.to_thread(lambda: Cluster(
                    name=cluster_status.name,
                    type=cluster_type.get('id'),
                    description = f'Proxmox {cluster_status.mode} cluster.',
                    tags=[tag.get('id', None)]
                ))
                
                device_type = await asyncio.to_thread(lambda: DeviceType(bootstrap_placeholder=True))
                role = await asyncio.to_thread(lambda: DeviceRole(bootstrap_placeholder=True))
                site = await asyncio.to_thread(lambda: Site(bootstrap_placeholder=True))
                
                if cluster is not None:
                    # TODO: Based on name.ip create Device IP Address
                    netbox_device = await asyncio.to_thread(lambda: Device(
                        name=node_obj.name,
                        tags=[tag.get('id', 0)],
                        cluster = cluster.get('id', Cluster(bootstrap_placeholder=True).get('id', 0)),
                        status='active',
                        description=f'Proxmox Node {node_obj.name}',
                        device_type=device_type.get('id', None),
                        role=role.get('id', None),
                        site=site.get('id', None),
                    ))
                
                    if type(netbox_device) != dict:
                        netbox_device = netbox_device.dict()
                
                await websocket.send_json(
                    {
                        'object': 'device',
                        'type': 'create',
                        'data': {
                            'completed': True,
                            'increment_count': 'yes',
                            'sync_status': completed_sync_html,
                            'rowid': node_obj.name,
                            'name': f"<a href='{netbox_device.get('display_url')}'>{netbox_device.get('name')}</a>",
                            'netbox_id': netbox_device.get('id'),
                            #'manufacturer': f"<a href='{netbox_device.get('manufacturer').get('url')}'>{netbox_device.get('manufacturer').get('name')}</a>",
                            'role': f"<a href='{netbox_device.get('role').get('url')}'>{netbox_device.get('role').get('name')}</a>",
                            'cluster': f"<a href='{netbox_device.get('cluster').get('url')}'>{netbox_device.get('cluster').get('name')}</a>",
                            'device_type': f"<a href='{netbox_device.get('device_type').get('url')}'>{netbox_device.get('device_type').get('model')}</a>",
                        }
                    }
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

async def create_interface_and_ip(
    tag: ProxboxTagDep,
    node_interface,
    node
):
    interface_type_mapping: dict = {
        'lo': 'loopback',
        'bridge': 'bridge',
        'bond': 'lag',
        'vlan': 'virtual',
    }
        
    node_cidr = getattr(node_interface, 'cidr', None)

    interface = Interface(
        device=node.get('id', 0),
        name=node_interface.iface,
        status='active',
        type=interface_type_mapping.get(node_interface.type, 'other'),
        tags=[tag.get('id', 0)],
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
            tags=[tag.get('id', 0)],
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

    return Interface.SchemaList(
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

@app.get('/virtualization/cluster-types/create')
async def create_cluster_types():
    # TODO
    pass

@app.get('/virtualization/clusters/create')
async def create_clusters(cluster_status: ClusterStatusDep):
    # TOOD
    pass

@app.get(
    '/extras/custom-fields/create',
    response_model=CustomField.SchemaList,
    response_model_exclude_none=True,
    response_model_exclude_unset=True
)
async def create_custom_fields(
    websocket = WebSocket
):
    custom_fields: list = [
        {
            "object_types": [
                "virtualization.virtualmachine"
            ],
            "type": "integer",
            "name": "proxmox_vm_id",
            "label": "VM ID",
            "description": "Proxmox Virtual Machine or Container ID",
            "ui_visible": "always",
            "ui_editable": "hidden",
            "weight": 100,
            "filter_logic": "loose",
            "search_weight": 1000,
            "group_name": "Proxmox"
        },
        {
            "object_types": [
                "virtualization.virtualmachine"
            ],
            "type": "boolean",
            "name": "proxmox_start_at_boot",
            "label": "Start at Boot",
            "description": "Proxmox Start at Boot Option",
            "ui_visible": "always",
            "ui_editable": "hidden",
            "weight": 100,
            "filter_logic": "loose",
            "search_weight": 1000,
            "group_name": "Proxmox"
        },
        {
            "object_types": [
                "virtualization.virtualmachine"
            ],
            "type": "boolean",
            "name": "proxmox_unprivileged_container",
            "label": "Unprivileged Container",
            "description": "Proxmox Unprivileged Container",
            "ui_visible": "if-set",
            "ui_editable": "hidden",
            "weight": 100,
            "filter_logic": "loose",
            "search_weight": 1000,
            "group_name": "Proxmox"
        },
        {
            "object_types": [
                "virtualization.virtualmachine"
            ],
            "type": "boolean",
            "name": "proxmox_qemu_agent",
            "label": "QEMU Guest Agent",
            "description": "Proxmox QEMU Guest Agent",
            "ui_visible": "if-set",
            "ui_editable": "hidden",
            "weight": 100,
            "filter_logic": "loose",
            "search_weight": 1000,
            "group_name": "Proxmox"
        },
        {
            "object_types": [
                "virtualization.virtualmachine"
            ],
            "type": "text",
            "name": "proxmox_search_domain",
            "label": "Search Domain",
            "description": "Proxmox Search Domain",
            "ui_visible": "if-set",
            "ui_editable": "hidden",
            "weight": 100,
            "filter_logic": "loose",
            "search_weight": 1000,
            "group_name": "Proxmox"
        }
    ]
    
    async def create_custom_field_task(custom_field: dict):
        return await asyncio.to_thread(lambda: CustomField(websocket=websocket, **custom_field))

    # Create Custom Fields
    return await asyncio.gather(*[
        create_custom_field_task(custom_field_dict)
        for custom_field_dict in custom_fields
    ])              

CreateCustomFieldsDep = Annotated[CustomField.SchemaList, Depends(create_custom_fields)]    


class VMConfig(BaseModel):
    parent: str | None = None
    digest: str | None = None
    swap: int | None = None
    searchdomain: str | None = None
    boot: str | None = None
    name: str | None = None
    cores: int | None = None
    scsihw: str | None = None
    vmgenid: str | None = None
    memory: int | None = None
    description: str | None = None
    ostype: str | None = None
    numa: int | None = None
    digest: str | None = None
    sockets: int | None = None
    cpulimit: int | None = None
    onboot: int | None = None
    cpuunits: int | None = None
    agent: int | None = None
    tags: str | None = None
    rootfs: str | None = None
    unprivileged: int | None = None
    nesting: int | None = None
    nameserver: str | None = None
    arch: str | None = None
    hostname: str | None = None
    rootfs: str | None = None
    features: str | None = None
    
    @model_validator(mode="before")
    @classmethod
    def validate_dynamic_keys(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        # Validate dynamic keys (e.g. scsi0, net0, etc.).
        if values:
            for key in values.keys():
                if not re.match(r'^(scsi|net|ide|unused|smbios)\d+$', key) and key not in cls.model_fields:
                    raise ValueError(f"Invalid key: {key}")
            return values

    class Config:
        extra = 'allow'

@app.get(
    '/proxmox/{node}/{type}/{vmid}/config',
    response_model=VMConfig,
    response_model_exclude_none=True,
    response_model_exclude_unset=True
)
async def get_vm_config(
    pxs: ProxmoxSessionsDep,
    cluster_status: ClusterStatusDep,
    name: str = Query(title="Cluster", description="Proxmox Cluster Name", default=None),
    node: str = Path(..., title="Node", description="Proxmox Node Name"),
    type: str = Path(..., title="Type", description="Proxmox VM Type"),
    vmid: int = Path(..., title="VM ID", description="Proxmox VM ID"),
):
    '''
    Loops through all Proxmox Clusters looking for a match in the node name.
    If found, it returns the VM Config.
    '''
    
    # Early error return.
    if not type:
        return {
            "message": "VM Type is required. Use 'qemu' or 'lxc'."
        }
    else:
        if type not in ('qemu', 'lxc'):
            return {
                "message": "Invalid VM Type. Use 'qemu' or 'lxc'."
            }

    try:
        config = None
        for px, cluster in zip(pxs, cluster_status):
            try:
                for cluster_node in cluster.node_list:
                    if str(node) == str(cluster_node.name):
                        if type == 'qemu':
                            config = px.session.nodes(node).qemu(vmid).config.get()
                        elif type == 'lxc':
                            config = px.session.nodes(node).lxc(vmid).config.get()
                            
                        if config: return config
            
            except ResourceException as error:
                raise ProxboxException(
                    message="Error getting VM Config",
                    python_exception=f"Error: {str(error)}"
                )

        if config is None:
            raise ProxboxException(
                message="VM Config not found.",
                detail="VM Config not found. Check if the 'node', 'type', and 'vmid' are correct."
            )            
    
    except ProxboxException:
        raise
    except Exception as error:
        raise ProxboxException(
            message="Unknown error getting VM Config. Search parameters probably wrong.",
            detail="Check if the node, type, and vmid are correct."
        )
    
@app.get('/virtualization/virtual-machines/create')
async def create_virtual_machines(
    pxs: ProxmoxSessionsDep,
    cluster_status: ClusterStatusDep,
    cluster_resources: ClusterResourcesDep,
    custom_fields: CreateCustomFieldsDep,
    tag: ProxboxTagDep,
    websocket = WebSocket
):
    async def _create_vm(cluster: dict):
        tasks = []  # Collect coroutines
        for cluster_name, resources in cluster.items():
            for resource in resources:
                if resource.get('type') in ('qemu', 'lxc'):
                    tasks.append(create_vm_task(cluster_name, resource))

        return await asyncio.gather(*tasks)  # Gather coroutines

    async def create_vm_task(cluster_name, resource):
        undefined_html = "<span class='badge text-bg-grey'><strong></strong>undefined</strong></span>"
        websocket_vm_json: dict = {
            'sync_status': sync_status_html,
            'name': undefined_html,
            'netbox_id': undefined_html,
            'status': undefined_html,
            'cluster': undefined_html,
            'device': undefined_html,
            'role': undefined_html,
            'vcpus': undefined_html,
            'memory': undefined_html,
            'disk': undefined_html,
            'vm_interfaces': undefined_html
        }
        
        vm_role_mapping: dict = {
            'qemu': {
                'name': 'Virtual Machine (QEMU)',
                'slug': 'virtual-machine-qemu',
                'color': '00ffff',
                'description': 'Proxmox Virtual Machine',
                'tags': [tag.get('id', 0)],
                'vm_role': True
            },
            'lxc': {
                'name': 'Container (LXC)',
                'slug': 'container-lxc',
                'color': '7fffd4',
                'description': 'Proxmox LXC Container',
                'tags': [tag.get('id', 0)],
                'vm_role': True
            },
            'undefined': {
                'name': 'Unknown',
                'slug': 'unknown',
                'color': '000000',
                'description': 'VM Type not found. Neither QEMU nor LXC.',
                'tags': [tag.get('id', 0)],
                'vm_role': True
            }
        }
        
        #vm_config = px.session.nodes(resource.get("node")).qemu(resource.get("vmid")).config.get()
     
        vm_type = resource.get('type', 'unknown')
        vm_config = await get_vm_config(
            pxs=pxs,
            cluster_status=cluster_status,
            node=resource.get("node"),
            type=vm_type,
            vmid=resource.get("vmid")
        )
        
 
        start_at_boot = True if vm_config.get('onboot', 0) == 1 else False
        qemu_agent = True if vm_config.get('agent', 0) == 1 else False
        unprivileged_container = True if vm_config.get('unprivileged', 0) == 1 else False
        search_domain = vm_config.get('searchdomain', None)
        
        #print(f'vm_config: {vm_config}')
        
        
        initial_vm_json = websocket_vm_json | {
            'completed': False,
            'rowid': str(resource.get('name')),
            'name': str(resource.get('name')),
            'cluster': str(cluster_name),
            'device': str(resource.get('node')),
        }

        await websocket.send_json(
            {
                'object': 'virtual_machine',
                'type': 'create',
                'data': initial_vm_json
            })

        try:
            print('\n')
            print('Creating Virtual Machine Dependents')
            cluster = await asyncio.to_thread(lambda: Cluster(name=cluster_name))
            device = await asyncio.to_thread(lambda: Device(name=resource.get('node')))
            role = await asyncio.to_thread(lambda: DeviceRole(**vm_role_mapping.get(vm_type)))
            
            
            print('> Virtual Machine Name: ', resource.get('name'))
            print('> Cluster: ', cluster.get('name'), cluster.get('id'), type(cluster.get('id')))
            print('> Device: ', device.get('name'), device.get('id'), type(device.get('id')))
            print('> Tag: ', tag.get('name'), tag.get('id'))
            print('> Role: ', role.get('name'), role.get('id'))
            print('Finish creating Virtual Machine Dependents')
            print('\n')
        except Exception as error:
            raise ProxboxException(
                message="Error creating Virtual Machine dependent objects (cluster, device, tag and role)",
                python_exception=f"Error: {str(error)}"
            )
            
        try:
            virtual_machine = await asyncio.to_thread(lambda: VirtualMachine(
                name=resource.get('name'),
                status=VirtualMachine.status_field.get(resource.get('status'), 'active'),
                cluster=cluster.get('id'),
                device=device.get('id'),
                vcpus=int(resource.get("maxcpu", 0)),
                memory=int(resource.get("maxmem")) // 1000000,  # Fixed typo 'mexmem'
                disk=int(resource.get("maxdisk", 0)) // 1000000,
                tags=[tag.get('id', 0)],
                role=role.get('id', 0),
                custom_fields={
                    "proxmox_vm_id": resource.get('vmid'),
                    "proxmox_start_at_boot": start_at_boot,
                    "proxmox_unprivileged_container": unprivileged_container,
                    "proxmox_qemu_agent": qemu_agent,
                    "proxmox_search_domain": search_domain,
                },
            ))

            
        except ProxboxException:
            raise
        except Exception as error:
            print(f'Error creating Virtual Machine in Netbox: {str(error)}')
            raise ProxboxException(
                message="Error creating Virtual Machine in Netbox",
                python_exception=f"Error: {str(error)}"
            )
            
        
        if type(virtual_machine) != dict:
            virtual_machine = virtual_machine.dict()
        
        def format_to_html(json: dict, key: str):
            return f"<a href='{json.get(key).get('url')}'>{json.get(key).get('name')}</a>"
        
        cluster_html = format_to_html(virtual_machine, 'cluster')
        device_html = format_to_html(virtual_machine, 'device')
        role_html = format_to_html(virtual_machine, 'role')
        
        status_html_choices = {
            'active': "<span class='text-bg-green badge p-1'>Active</span>",
            'offline': "<span class='text-bg-red badge p-1'>Offline</span>",
            'unknown': "<span class='text-bg-grey badge p-1'>Unknown</span>"
        }
        status_html = status_html_choices.get(virtual_machine.get('status').get('value'), status_html_choices.get('unknown'))
        
        vm_created_json: dict = initial_vm_json | {
            'increment_count': 'yes',
            'completed': True,
            'sync_status': completed_sync_html,
            'rowid': str(resource.get('name')),
            'name': f"<a href='{virtual_machine.get('display_url')}'>{virtual_machine.get('name')}</a>",
            'netbox_id': virtual_machine.get('id'),
            'status': status_html,
            'cluster': cluster_html,
            'device': device_html,
            'role': role_html,
            'vcpus': virtual_machine.get('vcpus'),
            'memory': virtual_machine.get('memory'),
            'disk': virtual_machine.get('disk'),
            'vm_interfaces': [],
        }
        
        # At this point, the Virtual Machine was created in NetBox. Left to create the interfaces.
        await websocket.send_json(
            {
                'object': 'virtual_machine',
                'type': 'create',
                'data': vm_created_json
            }
        )
        
        netbox_vm_interfaces: list = []
        
        if virtual_machine and vm_config:
            ''' 
            Create Virtual Machine Interfaces
            '''
            vm_networks: list = []
            network_id: int = 0 # Network ID
            while True:
                # Parse network information got from Proxmox to dict
                network_name = f'net{network_id}'
                
                vm_network_info = vm_config.get(network_name, None) # Example result: virtio=CE:59:22:67:69:b2,bridge=vmbr1,queues=20,tag=2010 
                if vm_network_info is not None:
                    net_fields = vm_network_info.split(',') # Example result: ['virtio=CE:59:22:67:69:b2', 'bridge=vmbr1', 'queues=20', 'tag=2010']
                    network_dict = dict([field.split('=') for field in net_fields]) # Example result: {'virtio': 'CE:59:22:67:69:b2', 'bridge': 'vmbr1', 'queues': '20', 'tag': '2010'}
                    vm_networks.append({network_name:network_dict})
                    
                    network_id += 1
                else:
                    # If no network found by increasing network id, break the loop.
                    break
            
            if vm_networks:
                for network in vm_networks:
                    print(f'vm: {virtual_machine.get('name')} - network: {network}')
                    # Parse the dict to valid netbox interface fields and Create Virtual Machine Interfaces
                    for interface_name, value in network.items():
                        # If 'bridge' value exists, create a bridge interface.
                        bridge_name = value.get('bridge', None)
                        bridge: dict = {}
                        if bridge_name:
                            bridge=VMInterface(
                                name=bridge_name,
                                virtual_machine=virtual_machine.get('id'),
                                type='bridge',
                                description=f'Bridge interface of Device {resource.get("node")}. The current NetBox modeling does not allow correct abstraction of virtual bridge.',
                                tags=[tag.get('id', 0)]
                            )
                        
                        if type(bridge) != dict:
                            bridge = bridge.dict()
                        
                        vm_interface = await asyncio.to_thread(lambda: VMInterface(
                            virtual_machine=virtual_machine.get('id'),
                            name=value.get('name', interface_name),
                            enabled=True,
                            bridge=bridge.get('id', None),
                            mac_address= value.get('virtio', value.get('hwaddr', None)), # Try get MAC from 'virtio' first, then 'hwaddr'. Else None.
                            tags=[tag.get('id', 0)]
                        ))
                        
                        
                        if type(vm_interface) != dict:
                            vm_interface = vm_interface.dict()
                        
                        netbox_vm_interfaces.append(vm_interface)
                        
                        # If 'ip' value exists and is not 'dhcp', create IP Address on NetBox.
                        interface_ip = value.get('ip', None)
                        if interface_ip and interface_ip != 'dhcp':
                            IPAddress(
                                address=interface_ip,
                                assigned_object_type='virtualization.vminterface',
                                assigned_object_id=vm_interface.get('id'),
                                status='active',
                                tags=[tag.get('id', 0)],
                            )
                            
                        # TODO: Create VLANs and other network related objects.
                        # 'tag' is the VLAN ID.
                        # 'bridge' is the bridge name.
        
        
        
        vm_created_with_interfaces_json: dict = vm_created_json | {
            'vm_interfaces': [f"<a href='{interface.get('display_url')}'>{interface.get('name')}</a>" for interface in netbox_vm_interfaces],
        }
        # Remove 'completed' and 'increment_count' keys from the dictionary so it does not affect progress count on GUI.
        vm_created_with_interfaces_json.pop('completed')
        vm_created_with_interfaces_json.pop('increment_count')
        
        await websocket.send_json(
            {
                'object': 'virtual_machine',
                'type': 'create',
                'data': vm_created_with_interfaces_json
            }
        )
        
        
        # Lamba is necessary to treat the object instantiation as a coroutine/function.
        return virtual_machine

        """""
        proxmox_start_at_boot": resource.get(''),
        "proxmox_unprivileged_container": unprivileged_container,
        "proxmox_qemu_agent": qemu_agent,
        "proxmox_search_domain": search_domain,
        """
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

@app.websocket("/ws")
async def websocket_endpoint(
    nb: NetboxSessionDep,
    pxs: ProxmoxSessionsDep,
    cluster_status: ClusterStatusDep,
    cluster_resources: ClusterResourcesDep,
    custom_fields: CreateCustomFieldsDep,
    tag: ProxboxTagDep,
    websocket: WebSocket
):
    try:
        await websocket.accept()
        connection_open = True
        await websocket.send_text('Connected!')
    except Exception as error:
        print(f"Error while accepting WebSocket connection: {error}")
        try:
            await websocket.close()
        except Exception as error:
            print(f"Error while closing WebSocket connection: {error}")
    
    # 'data' is the message received from the WebSocket.
    data = None

    try:
        while True:
            try:
                data = await websocket.receive_text()
                print(f'Received message: {data}')
            except Exception as error:
                print(f"Error while receiving data from WebSocket: {error}")
                break
            
            # Sync Nodes
            sync_nodes_function = create_proxmox_devices(
                clusters_status=cluster_status,
                nb=nb,
                node=None,
                websocket=websocket,
                tag=tag
            )
            
            # Sync Virtual Machines
            sync_vms_function = create_virtual_machines(
                pxs=pxs,
                cluster_status=cluster_status,
                cluster_resources=cluster_resources,
                custom_fields=custom_fields,
                websocket=websocket,
                tag=tag
            )
            
            if data == "Full Update Sync":
                # Sync Nodes
                sync_nodes = await create_proxmox_devices(
                    clusters_status=cluster_status,
                    nb=nb,
                    node=None,
                    websocket=websocket,
                    tag=tag
                )
                
                if sync_nodes: 
                    # Sync Virtual Machines
                    await create_virtual_machines(
                        pxs=pxs,
                        cluster_status=cluster_status,
                        cluster_resources=cluster_resources,
                        custom_fields=custom_fields,
                        websocket=websocket,
                        tag=tag
                    )
                
            if data == "Sync Nodes":
                await create_proxmox_devices(
                    clusters_status=cluster_status,
                    nb=nb,
                    node=None,
                    websocket=websocket,
                    tag=tag
                )
                
            elif data == "Sync Virtual Machines":
                await create_virtual_machines(
                    pxs=pxs,
                    cluster_status=cluster_status,
                    cluster_resources=cluster_resources,
                    custom_fields=custom_fields,
                    websocket=websocket,
                    tag=tag
                )
                
            else:
                await websocket.send_denial_response("Invalid command.")

    except WebSocketDisconnect as error:
        print(f"WebSocket Disconnected: {error}")
        connection_open = False
    finally:
        if connection_open and websocket.client_state.CONNECTED:
            await websocket.close(code=1000, reason=None)
