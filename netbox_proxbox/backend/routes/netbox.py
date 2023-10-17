from fastapi import APIRouter, Depends

from typing import Annotated, Any

from netbox_proxbox.backend.schemas import PluginConfig
from netbox_proxbox.backend.schemas.netbox import NetboxSessionSchema
from netbox_proxbox.backend.session.netbox import NetboxSession
from netbox_proxbox.backend.routes.proxbox import netbox_settings

router = APIRouter()

@router.get("/")
async def netbox(
    netbox_settings: Annotated[NetboxSessionSchema, Depends(netbox_settings)],
):
    
    return NetboxSession(netbox_settings)

@router.get("/status")
async def netbox_status(
    nb: Annotated[Any, Depends(netbox)]
):
    return nb.nb_session.status()

@router.get("/devices")
async def netbox_devices(nb: Annotated[Any, Depends(netbox)]):
    "Return a list of all devices registered on Netbox."
    raw_list = []
    
    device_list = nb.nb_session.dcim.device_roles.all()
    for device in device_list:
        raw_list.append(device)
    
    return raw_list
    