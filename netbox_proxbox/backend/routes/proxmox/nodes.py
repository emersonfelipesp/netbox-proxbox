from fastapi import APIRouter

router = APIRouter()

from netbox_proxbox.backend.session.proxmox import ProxmoxSessionsDep
from netbox_proxbox.backend.schemas.proxmox import ResponseNodeList

@router.get("/", response_model=ResponseNodeList)
async def nodes(
    pxs: ProxmoxSessionsDep
):
    json_result = []
    
    for px in pxs:
        json_result.append(
            {
                px.name: px.session.nodes.get()
            }
        )
    
    return json_result