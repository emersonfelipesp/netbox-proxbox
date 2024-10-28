from fastapi import APIRouter, Path

from typing import Annotated

from proxmoxer.core import ResourceException

from netbox_proxbox.backend.session.proxmox import ProxmoxSessionsDep

router = APIRouter()

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