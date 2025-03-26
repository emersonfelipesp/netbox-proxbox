import traceback

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, Depends, Query, Path
from starlette.websockets import WebSocketState
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from proxmoxer.core import ResourceException

import re

from pydantic import BaseModel, Field, conint, constr, model_validator, root_validator, Extra
from typing import Annotated, Optional, Dict, Any, List

import asyncio

# pynetbox API Imports (from v6.0.0 plugin uses pynetbox-api package)
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
from pynetbox_api import RawNetBoxSession

# Proxbox API Imports
from proxbox_api.exception import ProxboxException



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
from proxbox_api.routes.netbox import router as netbox_router, GetNetBoxEndpoint, get_netbox_endpoints


# Sessions
from proxbox_api.session.proxmox import ProxmoxSessionsDep


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

configuration = None
default_config: dict = {}
plugin_configuration: dict = {}
proxbox_cfg: dict = {}  

PROXBOX_PLUGIN_NAME: str = "netbox_proxbox"

# Init FastAPI
app = FastAPI(  
    title="Proxbox Backend",
    description="## Proxbox Backend made in FastAPI framework",
    version="0.0.1"
)


from sqlmodel import select
from pynetbox_api.database import NetBoxEndpoint, get_session
from sqlalchemy.exc import OperationalError

netbox_endpoint = None
database_session = None
try:
    database_session = next(get_session())
except OperationalError as error:
    print(error)
    pass

if database_session:    
    try:
        netbox_endpoints = database_session.exec(select(NetBoxEndpoint)).all()
    except OperationalError as error:
        # If table does not exist, create it.
        from pynetbox_api.database import create_db_and_tables
        create_db_and_tables()
        netbox_endpoints = database_session.exec(select(NetBoxEndpoint)).all()
        

origins = []
"""
CORS Middleware
"""
if netbox_endpoints:
    for netbox_endpoint in netbox_endpoints:
        protocol = "https" if netbox_endpoint.verify_ssl else "http"
        origins.extend([
            f"{protocol}://{netbox_endpoint.domain}",
            f"{protocol}://{netbox_endpoint.domain}:80",
            f"{protocol}://{netbox_endpoint.domain}:443",
            f"{protocol}://{netbox_endpoint.domain}:8000"
        ])
        
# Add default development origins
origins.extend([
    "https://127.0.0.1:443",
    "http://127.0.0.1:80", 
    "http://127.0.0.1:8000"
])

print(origins)

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

def return_status_html(status: str, use_css: bool):
    undefined_html_raw = "undefined"
    undefined_html_css = f"<span class='badge text-bg-grey'><strong>{undefined_html_raw}</strong></span>"
    undefined_html = undefined_html_css if use_css else undefined_html_raw
         
    sync_status_html_css = "<span class='text-bg-yellow badge p-1' title='Syncing VM' ><i class='mdi mdi-sync'></i></span>"
    sync_status_html_raw = "syncing"
    sync_status_html = sync_status_html_css if use_css else sync_status_html_raw

    completed_sync_html_css = "<span class='text-bg-green badge p-1' title='Synced VM'><i class='mdi mdi-check'></i></span>"
    completed_sync_html_raw = "completed"
    completed_sync_html = completed_sync_html_css if use_css else completed_sync_html_raw

    if status == "syncing":
        return sync_status_html
    elif status == "completed":
        return completed_sync_html
    return undefined_html


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
    
from pynetbox_api.cache import global_cache

@app.get('/cache')
async def get_cache():
    return global_cache.return_cache()
 
@app.get('/dcim/devices')
async def create_devices():
    return {
        "message": "Devices created"
    }

@app.get('/clear-cache')
async def clear_cache():
    global_cache.clear_cache()
    return {
        "message": "Cache cleared"
    }


from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class SyncProcessIn(BaseModel):
    name: str
    sync_type: str
    status: str
    started_at: datetime
    completed_at: datetime

class SyncProcess(SyncProcessIn):
    id: int
    url: str
    display: str
    
# Example instance
example_sync_process = SyncProcess(
    id=1,
    url="https://10.0.30.200/api/plugins/proxbox/sync-processes/1/",
    display="teste (all)",
    name="teste",
    sync_type="all",
    status="not-started",
    started_at="2025-03-13T15:08:09.051478Z",
    completed_at="2025-03-13T15:08:09.051478Z",

)

@app.get('/sync-processes', response_model=List[SyncProcess])
async def get_sync_processes():
    """
    Get all sync processes from Netbox.
    """
    
    nb = RawNetBoxSession
    sync_processes = [process.serialize() for process in nb.plugins.proxbox.__getattr__('sync-processes').all()]
    return sync_processes

@app.post('/sync-processes', response_model=SyncProcess)
async def create_sync_process():
    """
    Create a new sync process in Netbox.
    """
    
    print(datetime.now())
    
    nb = RawNetBoxSession
    sync_process = nb.plugins.proxbox.__getattr__('sync-processes').create(
        name=f"sync-process-{datetime.now()}",
        sync_type="all",
        status="not-started",
        started_at=str(datetime.now()),
        completed_at=str(datetime.now()),
    )
    
    return sync_process
'''
@app.websocket("/ws-test")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    while True:
        await websocket.send_text(f"Successful")
'''
@app.get(
    '/dcim/devices/create',
    response_model=Device.SchemaList,
    response_model_exclude_none=True,
    response_model_exclude_unset=True,
)
async def create_proxmox_devices(
    clusters_status: ClusterStatusDep,
    tag: ProxboxTagDep,
    websocket: WebSocket = None,
    node: str | None = None,
    use_websocket: bool = False,
    use_css: bool = False
):
    # GET /api/plugins/proxbox/sync-processes/
    nb = RawNetBoxSession
    start_time = datetime.now()
    sync_process = None
    
    try:    
        sync_process = nb.plugins.proxbox.__getattr__('sync-processes').create({
            'name': f"sync-devices-{start_time}",
            'sync_type': "devices",
            'status': "not-started",
            'started_at': str(start_time),
            'completed_at': None,
            'runtime': None,
            'tags': [tag.get('id', 0)],
        })

    except Exception as error:
        print(error)
        pass
    
    device_list: list = []
    
    for cluster_status in clusters_status:
        for node_obj in cluster_status.node_list:
            if use_websocket:
                await websocket.send_json(
                    {
                        'object': 'device',
                        'type': 'create',
                        'data': {
                            'completed': False,
                            'sync_status': return_status_html('syncing', use_css),
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
                
                netbox_device = None
                if cluster is not None:
                    # TODO: Based on name.ip create Device IP Address
                    netbox_device = await asyncio.to_thread(lambda: Device(
                        name=node_obj.name,
                        tags=[tag.get('id', 0)],
                        cluster = cluster.get('id'),
                        status='active',
                        description=f'Proxmox Node {node_obj.name}',
                        device_type=device_type.get('id', None),
                        role=role.get('id', None),
                        site=site.get('id', None),
                    ))
                    
                print(f'netbox_device: {netbox_device}')
                
                if netbox_device is None and all([use_websocket, websocket]):
                    await websocket.send_json(
                        {
                            'object': 'device',
                            'type': 'create',
                            'data': {
                                'completed': True,
                                'increment_count': 'yes',
                                'sync_status': return_status_html('completed', use_css),
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
    
    # Send end message to websocket to indicate that the creation of devices is finished.
    if all([use_websocket, websocket]):
        await websocket.send_json({'object': 'device', 'end': True})
    
    # Clear cache after creating devices.
    global_cache.clear_cache()
    
    if sync_process:
        end_time = datetime.now()
        sync_process.status = "completed"
        sync_process.completed_at = str(end_time)
        sync_process.runtime = float((end_time - start_time).total_seconds())
        sync_process.save()
    
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
        return await asyncio.to_thread(lambda: CustomField(**custom_field))

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
    websocket = WebSocket,
    use_css: bool = False,
    use_websocket: bool = False
):
    '''
    Creates a new virtual machine in Netbox.
    '''
    
    # GET /api/plugins/proxbox/sync-processes/
    nb = RawNetBoxSession
    start_time = datetime.now()
    sync_process = None
    try:
        sync_process = nb.plugins.proxbox.__getattr__('sync-processes').create(
            name=f"sync-virtual-machines-{start_time}",
            sync_type="virtual-machines",
            status="not-started",
            started_at=str(start_time),
            completed_at=None,
            runtime=None,
            tags=[tag.get('id', 0)],
        )
    except Exception as error:
        print(error)
        pass
    
    async def _create_vm(cluster: dict):
        tasks = []  # Collect coroutines
        for cluster_name, resources in cluster.items():
            for resource in resources:
                if resource.get('type') in ('qemu', 'lxc'):
                    tasks.append(create_vm_task(cluster_name, resource))

        return await asyncio.gather(*tasks)  # Gather coroutines

    async def create_vm_task(cluster_name, resource):
        undefined_html = return_status_html('undefined', use_css)
        
        websocket_vm_json: dict = {
            'sync_status': return_status_html('syncing', use_css),
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

        if all([use_websocket, websocket]):
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
        
        
        active_raw = "Active"
        active_css = "<span class='text-bg-green badge p-1'>Active</span>"
        active_html = active_css if use_css else active_raw
        
        offline_raw = "Offline"
        offline_css = "<span class='text-bg-red badge p-1'>Offline</span>"
        offline_html = offline_css if use_css else offline_raw
        
        unknown_raw = "Unknown"
        unknown_css = "<span class='text-bg-grey badge p-1'>Unknown</span>"
        unknown_html = unknown_css if use_css else unknown_raw
        
        status_html_choices = {
            'active': active_html,
            'offline': offline_html,
            'unknown': unknown_html
        }
        
        status_html = status_html_choices.get(virtual_machine.get('status').get('value'), status_html_choices.get('unknown'))
    
        name_html_css = f"<a href='{virtual_machine.get('display_url')}'>{virtual_machine.get('name')}</a>"
        name_html_raw = f"{virtual_machine.get('name')}"
        name_html = name_html_css if use_css else name_html_raw
        
        vm_created_json: dict = initial_vm_json | {
            'increment_count': 'yes',
            'completed': True,
            'sync_status': return_status_html('completed', use_css),
            'rowid': str(resource.get('name')),
            'name': name_html,
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
        if all([use_websocket, websocket]):
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
        
        if all([use_websocket, websocket]):
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
    
    
    
    # Return the created virtual machines.
    result_list = await asyncio.gather(*[_create_vm(cluster) for cluster in cluster_resources], return_exceptions=True)

    print('result_list: ', result_list)

    # Send end message to websocket to indicate that the creation of virtual machines is finished.
    if all([use_websocket, websocket]):
        await websocket.send_json({'object': 'virtual_machine', 'end': True})

    # Clear cache after creating virtual machines.
    global_cache.clear_cache()
    
    if sync_process:
        end_time = datetime.now()
        sync_process.status = "completed"
        sync_process.completed_at = str(end_time)
        sync_process.runtime = float((end_time - start_time).total_seconds())
        sync_process.save()
    
    return result_list
 
 
@app.get(
    '/virtualization/virtual-machines/',
    response_model=VirtualMachine.SchemaList,
    response_model_exclude_none=True,
    response_model_exclude_unset=True
)
async def get_virtual_machines():
    virtual_machine = VirtualMachine()
    return virtual_machine.all()


@app.get(
    '/virtualization/virtual-machines/{id}',
    response_model=VirtualMachine.Schema,
    response_model_exclude_none=True,
    response_model_exclude_unset=True
)
async def get_virtual_machine(id: int):
    try:
        virtual_machine = VirtualMachine().get(id=id)
        if virtual_machine:
            return virtual_machine
        else:
            return {}
    except Exception as error:
        return {}

class CPU(BaseModel):
    cores: int
    sockets: int
    type: str
    usage: int

class Memory(BaseModel):
    total: int
    used: int
    usage: int

class Disk(BaseModel):
    id: str
    storage: str
    size: int
    used: int
    usage: int
    format: str
    path: str

class Network(BaseModel):
    id: str
    model: str
    bridge: str
    mac: str
    ip: str
    netmask: str
    gateway: str

class Snapshot(BaseModel):
    id: str
    name: str
    created: str
    description: str

class Backup(BaseModel):
    id: str
    storage: str
    created: str
    size: int
    status: str

class VirtualMachineSummary(BaseModel):
    id: str
    name: str
    status: str
    node: str
    cluster: str
    os: str
    description: str
    uptime: str
    created: str
    cpu: CPU
    memory: Memory
    disks: List[Disk]
    networks: List[Network]
    snapshots: List[Snapshot]
    backups: List[Backup]
        
@app.get(
    '/virtualization/virtual-machines/summary/example',
    response_model=VirtualMachineSummary,
    response_model_exclude_none=True,
    response_model_exclude_unset=True
)
async def get_virtual_machine_summary_example():
   

    # Example usage
    vm_summary = VirtualMachineSummary(
        id="vm-102",
        name="db-server-01",
        status="running",
        node="pve-node-02",
        cluster="Production Cluster",
        os="CentOS 8",
        description="Primary database server for production applications",
        uptime="43 days, 7 hours, 12 minutes",
        created="2023-01-15",
        cpu=CPU(cores=8, sockets=1, type="host", usage=32),
        memory=Memory(total=16384, used=10240, usage=62),
        disks=[
            Disk(id="scsi0", storage="local-lvm", size=102400, used=67584, usage=66, format="raw", path="/dev/pve/vm-102-disk-0"),
            Disk(id="scsi1", storage="local-lvm", size=409600, used=215040, usage=52, format="raw", path="/dev/pve/vm-102-disk-1"),
        ],
        networks=[
            Network(id="net0", model="virtio", bridge="vmbr0", mac="AA:BB:CC:DD:EE:FF", ip="10.0.0.102", netmask="255.255.255.0", gateway="10.0.0.1"),
            Network(id="net1", model="virtio", bridge="vmbr1", mac="AA:BB:CC:DD:EE:00", ip="192.168.1.102", netmask="255.255.255.0", gateway="192.168.1.1"),
        ],
        snapshots=[
            Snapshot(id="snap1", name="pre-update", created="2023-05-10 14:30:00", description="Before system update"),
            Snapshot(id="snap2", name="db-config-change", created="2023-06-15 09:45:00", description="After database configuration change"),
            Snapshot(id="snap3", name="monthly-backup", created="2023-07-01 00:00:00", description="Monthly automated snapshot"),
        ],
        backups=[
            Backup(id="backup1", storage="backup-nfs", created="2023-07-01 01:00:00", size=75840, status="successful"),
            Backup(id="backup2", storage="backup-nfs", created="2023-06-01 01:00:00", size=72560, status="successful"),
            Backup(id="backup3", storage="backup-nfs", created="2023-05-01 01:00:00", size=70240, status="successful"),
        ]
    )
    
    return vm_summary

@app.get(
    '/virtualization/virtual-machines/{id}/summary',
)
async def get_virtual_machine_summary(id: int):
    pass

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
#app.include_router(proxbox_router, prefix="/proxbox", tags=["proxbox"])
#app.include_router(pb_cluster_router, prefix="/proxbox/clusters", tags=["proxbox / clusters"])

@app.websocket('/')
async def base_websocket(websocket: WebSocket):
    count = 0
    
    await websocket.accept()
    try:
        while True:
            #data = await websocket.receive_text()
            #await websocket.send_text(f"Message text was: {data}")
            count = count+1
            await websocket.send_text(f'Message: {count}')
            await asyncio.sleep(2)
            
    except WebSocketDisconnect:
        print("WebSocket connection closed")

@app.get("/ws-test-http")
async def websocket_endpoint(
    pxs: ProxmoxSessionsDep,
    cluster_status: ClusterStatusDep,
    cluster_resources: ClusterResourcesDep,
    custom_fields: CreateCustomFieldsDep,
    tag: ProxboxTagDep,
):
    print(NetboxSessionDep)
    print(ProxmoxSessionsDep)
    print(ClusterStatusDep)
    print(ClusterResourcesDep)
    print(CreateCustomFieldsDep)
    print(ProxboxTagDep)
    print('route ws-test-http reached')

@app.websocket("/ws/virtual-machines")
async def websocket_endpoint(
    pxs: ProxmoxSessionsDep,
    cluster_status: ClusterStatusDep,
    cluster_resources: ClusterResourcesDep,
    custom_fields: CreateCustomFieldsDep,
    tag: ProxboxTagDep,
    websocket: WebSocket,
):
    print('route ws/virtual-machines reached')
    
    connection_open = False
    
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
            
    data = None
    
    await create_virtual_machines(
        pxs=pxs,
        cluster_status=cluster_status,
        cluster_resources=cluster_resources,
        custom_fields=custom_fields,
        websocket=websocket,
        tag=tag,
        use_css=False
    )
                

@app.get('/full-update')
async def full_update_sync(
    pxs: ProxmoxSessionsDep,
    cluster_status: ClusterStatusDep,
    cluster_resources: ClusterResourcesDep,
    custom_fields: CreateCustomFieldsDep,
    tag: ProxboxTagDep
):
    start_time = datetime.now()
    sync_process = None

    nb = RawNetBoxSession
    try:
        sync_process = nb.plugins.proxbox.__getattr__('sync-processes').create(
            name=f"sync-all-{start_time}",
            sync_type="all",
            status="not-started",
            started_at=str(start_time),
            completed_at=None,
            runtime=None,
            tags=[tag.get('id', 0)],
        )
    except Exception as error:
        print(error)
        pass

    try:
        # Sync Nodes
        sync_nodes = await create_proxmox_devices(
            clusters_status=cluster_status,
                node=None,
                tag=tag,
                use_websocket=False
            )
    except Exception as error:
        print(error)
        raise ProxboxException(message=f"Error while syncing nodes.", python_exception=str(error))

    if sync_nodes: 
        # Sync Virtual Machines
        try:
            sync_vms = await create_virtual_machines(
                pxs=pxs,
                cluster_status=cluster_status,
                cluster_resources=cluster_resources,
                custom_fields=custom_fields,
                tag=tag,
                use_websocket=False
            )
        except Exception as error:
            print(error)
            raise ProxboxException(message=f"Error while syncing virtual machines.", python_exception=str(error))

    if sync_process:
        end_time = datetime.now()
        sync_process.status = "completed"
        sync_process.completed_at = str(end_time)
        sync_process.runtime = float((end_time - start_time).total_seconds())
        sync_process.save()
        
        print(sync_process)
        print(sync_process.runtime)
    return sync_nodes, sync_vms

    
@app.websocket("/ws")
async def websocket_endpoint(
    pxs: ProxmoxSessionsDep,
    cluster_status: ClusterStatusDep,
    cluster_resources: ClusterResourcesDep,
    custom_fields: CreateCustomFieldsDep,
    tag: ProxboxTagDep,
    websocket: WebSocket,
):
    connection_open = False
    
    nb = RawNetBoxSession
    
    print('route ws reached')
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

    await websocket.send_text('Connected 2!')
    
    try:
        while True:
            try:
                data = await websocket.receive_text()
                print(f'Received message: {data}')
                await websocket.send_text(f'Received message: {data}')
            except Exception as error:
                print(f"Error while receiving data from WebSocket: {error}")
                break
            
            # Sync Nodes
            sync_nodes_function = create_proxmox_devices(
                clusters_status=cluster_status,
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
                tag=tag,
                use_websocket=True
            )
            
            if data == "Full Update Sync":
                sync_process = None
                
                try:
                    sync_process = nb.plugins.proxbox.__getattr__('sync-processes').create(
                        name=f"sync-process-{datetime.now()}",
                        sync_type="all",
                        status="not-started",
                        started_at=str(datetime.now()),
                    )
                except Exception as error:
                    print(error)
                    pass
                
                # Sync Nodes
                sync_nodes = await create_proxmox_devices(
                    clusters_status=cluster_status,
                    node=None,
                    websocket=websocket,
                    tag=tag,
                    use_websocket=True
                )
                
                if sync_nodes: 
                    # Sync Virtual Machines
                    await create_virtual_machines(
                        pxs=pxs,
                        cluster_status=cluster_status,
                        cluster_resources=cluster_resources,
                        custom_fields=custom_fields,
                        websocket=websocket,
                        tag=tag,
                        use_websocket=True
                    )
                
                if sync_process:
                    sync_process.status = "completed"
                    sync_process.completed_at = str(datetime.now())
                    sync_process.save()
                
            if data == "Sync Nodes":
                print('Sync Nodes')
                await websocket.send_text('Sync Nodes')
                await create_proxmox_devices(
                    clusters_status=cluster_status,
                    node=None,
                    websocket=websocket,
                    tag=tag,
                    use_websocket=True
                )
                
            elif data == "Sync Virtual Machines":
                await create_virtual_machines(
                    pxs=pxs,
                    cluster_status=cluster_status,
                    cluster_resources=cluster_resources,
                    custom_fields=custom_fields,
                    websocket=websocket,
                    tag=tag,
                    use_websocket=True
                )
                
            else:
                await websocket.send_text(f"Invalid command: {data}")
                await websocket.send_text("Valid commands: 'Sync Nodes', 'Sync Virtual Machines', 'Full Update Sync'")
                #await websocket.send_denial_response("Invalid command.")

    except WebSocketDisconnect as error:
        print(f"WebSocket Disconnected: {error}")
        connection_open = False
    finally:
        if connection_open and websocket.client_state.CONNECTED:
            await websocket.close(code=1000, reason=None)
