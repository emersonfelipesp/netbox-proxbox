from fastapi import APIRouter, Path, Depends
from pydantic import BaseModel
from typing import Annotated

from proxmoxer.core import ResourceException

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