from fastapi import APIRouter, Path

from typing import Annotated

from proxmoxer.core import ResourceException

router = APIRouter()

from netbox_proxbox.backend.session.proxmox import ProxmoxSessionsDep
from netbox_proxbox.backend.schemas.proxmox import ResponseNodeList



"""
@router.get("/", response_model=ResponseNodeList)
async def nodes(pxs: ProxmoxSessionsDep):
    json_result = []
    
    for px in pxs:
        json_result.append(
            {
                px.name: px.session(path).get()
            }
        )
    
    return json_result
"""

@router.get("/teste")
async def test():
    return "teste"

@router.get("/{node}")
async def nodes(
    pxs: ProxmoxSessionsDep,
    node: Annotated[str, Path(title="Proxmox Node", description="Proxmox Node name (ex. 'pve01').")],
):
    json_result = []
    
    for px in pxs:
        json_result.append(
            {
                px.name: px.session(f"/nodes/{node}").get()
            }
        )
    
    return json_result

@router.get("/{node}/qemu")
async def nodes(
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
            pass
    
    return json_result