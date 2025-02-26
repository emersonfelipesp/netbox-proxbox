from fastapi import APIRouter, Path, Depends, Query
from pydantic import BaseModel
from typing import Annotated
from enum import Enum
from proxmoxer.core import ResourceException

from proxbox_api.exception import ProxboxException
from proxbox_api.session.proxmox import ProxmoxSessionsDep

router = APIRouter()

class NodeSchema(BaseModel):
    node: str
    status: str
    cpu: float
    level: str | None = None
    maxcpu: int
    maxmem: float
    mem: float
    ssl_fingerprint: str
    
NodeSchemaList = list[dict[str, NodeSchema]]

@router.get("/", response_model=NodeSchemaList)
async def get_node(pxs: ProxmoxSessionsDep) -> NodeSchemaList:
    # Return all
    return NodeSchemaList([{
        px.name: NodeSchema(**px.session(f"/nodes/").get()[0])
    } for px in pxs])

ProxmoxNodeDep = Annotated[NodeSchemaList, Depends(get_node)]

class InterfaceTypeChoices(str, Enum):
    bridge = "bridge"
    bond = "bond"
    eth = "eth"
    alias = "alias"
    vlan = "vlan"
    OVSBridge = "OVSBridge"
    OVSBond = "OVSBond"
    OVSPort = "OVSPort"
    OVSIntPort = "OVSIntPort"
    any_bridge = "any_bridge"
    any_local_bridge = "any_local_bridge"

class ProxmoxNodeInterfaceSchema(BaseModel):
    active: int | None = None
    address: str | None = None
    netmask: str | None = None
    gateway: str | None = None
    autostart: int | None = None
    bond_miimon: int | None = None
    bond_mode: str | None = None
    slaves: str | None = None
    bridge_fd: str | None = None
    bridge_ports: str | None = None
    bridge_stp: str | None = None
    brdige_vlan_aware: int | None = None
    cidr: str | None = None
    comments: str | None = None
    exists: int | None = None
    families: list[str] | None = None
    iface: str | None = None
    method: str | None = None
    method6: str | None = None
    priority: int | None = None
    type: str | None = None
    vlan_id: str | None = None
    vlan_raw_device: str | None = None

ProxmoxNodeInterfaceSchemaList = list[ProxmoxNodeInterfaceSchema]

@router.get('/{node}/network',
    response_model_exclude_none=True,
    response_model_exclude_unset=True,
    response_model=ProxmoxNodeInterfaceSchemaList
)
async def get_node_network(
    pxs: ProxmoxSessionsDep,
    node: Annotated[
        str,
        Path(
            title="Proxmox Node",
            description="Proxmox Node Name (ex. 'pve01')."
        )
    ],
    type: Annotated[
        InterfaceTypeChoices,
        Query(
            title="Network Type",
            description="Network Type (ex. 'eth0')."
        )
    ]  = None
) -> ProxmoxNodeInterfaceSchemaList:
    for px in pxs:
        interfaces = []
        try:
            if type:
                node_networks = px.session(f'/nodes/{node}/network').get(type=type)
            else:
                node_networks = px.session(f'/nodes/{node}/network').get()
        except ResourceException as error:
            raise ProxboxException(
                message='Error getting node network interfaces from Proxmox',
                python_exception=str(error)
            )
            
        for interface in node_networks:
            vlan_id = interface.get('vlan-id')
            if vlan_id:
                interface.pop('vlan-id')
                interface['vlan_id'] = vlan_id

            vlan_raw_device = interface.get('vlan-raw-device')
            if vlan_raw_device:
                interface.pop('vlan-raw-device')
                interface['vlan_raw_device'] = vlan_raw_device
                
            interfaces.append(ProxmoxNodeInterfaceSchema(**interface))
        
        return ProxmoxNodeInterfaceSchemaList(interfaces)

ProxmoxNodeInterfacesDep = Annotated[ProxmoxNodeInterfaceSchemaList, Depends(get_node_network)]

@router.get("/{node}/qemu")
async def node_qemu(
    pxs: ProxmoxSessionsDep,
    node: Annotated[str, Path(title="Proxmox Node", description="Proxmox Node name (ex. 'pve01').")],
):
    json_result = []
    
    for px in pxs:
        try:
            json_result.append(
                {
                    px.name: px.session(f"/nodes/{node}/qemu").get()
                }
            )
        except ResourceException as error:
            print(f"Error: {error}")
            pass
    
    return json_result