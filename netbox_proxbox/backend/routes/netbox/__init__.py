from fastapi import APIRouter, Depends

from typing import Annotated, Any

from netbox_proxbox.backend.routes.proxbox import netbox_settings
from netbox_proxbox.backend.session.netbox import NetboxSessionDep

# FastAPI Router
router = APIRouter()

#
# Endpoints: /netbox/<endpoint>
#
@router.get("/status")
async def netbox_status(
    nb: NetboxSessionDep
):
    return nb.session.status()

@router.get("/devices")
async def netbox_devices(nb: NetboxSessionDep):
    "Return a list of all devices registered on Netbox."
    raw_list = []
    
    device_list = nb.session.dcim.device_roles.all()
    for device in device_list:
        raw_list.append(device)
    
    return raw_list

@router.get("/openapi")
async def netbox_devices(nb: NetboxSessionDep):
    
    output = nb.session.openapi()
    return output

@router.get("/")
async def netbox(
    status: Annotated[Any, Depends(netbox_status)],
    config: Annotated[Any, Depends(netbox_settings)],
    nb: NetboxSessionDep,
):
    return {
        "config": config,
        "status": status,
        "proxbox_tag": nb.tag
    }



