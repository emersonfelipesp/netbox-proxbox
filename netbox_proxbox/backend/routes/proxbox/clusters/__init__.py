from fastapi import APIRouter, Depends

from typing import Annotated, Any

# Import Both Proxmox Sessions and Netbox Session Dependencies
from netbox_proxbox.backend.session.proxmox import ProxmoxSessionsDep
from netbox_proxbox.backend.session.netbox import NetboxSessionDep

router = APIRouter()

@router.get("/")
async def proxbox_get_clusters(
    pxs: ProxmoxSessionsDep,
    nb: NetboxSessionDep
):
    """Automatically sync Proxmox Clusters with Netbox Clusters"""
    pass
    # for px in pxs:
    #     nb.
    #     json_response.append(
    #         {
    #             px.name: px.session.version.get()
    #         }
    #     )