from fastapi import APIRouter, Depends

from typing import Annotated, Any

from netbox_proxbox.backend.schemas import PluginConfig
from netbox_proxbox.backend.schemas.netbox import NetboxSessionSchema
from netbox_proxbox.backend.session.netbox import NetboxSession
from netbox_proxbox.backend.routes.proxbox import netbox_settings

router = APIRouter()



async def netbox_session(
    netbox_settings: Annotated[NetboxSessionSchema, Depends(netbox_settings)],
):
    """Instantiate 'NetboxSession' class with user parameters and return Netbox  HTTP connection to make API calls"""
    return NetboxSession(netbox_settings).session

NetboxSessionDep = Annotated[Any, Depends(netbox_session)]

@router.get("/status")
async def netbox_status(
    nb: NetboxSessionDep
):
    return nb.status()

@router.get("/devices")
async def netbox_devices(nb: NetboxSessionDep):
    "Return a list of all devices registered on Netbox."
    raw_list = []
    
    device_list = nb.nb_session.dcim.device_roles.all()
    for device in device_list:
        raw_list.append(device)
    
    return raw_list

@router.get("/openapi")
async def netbox_devices(nb: NetboxSessionDep):
    return nb.openapi()

@router.get("/")
async def netbox(
    status: Annotated[Any, Depends(netbox_status)],
    config: Annotated[Any, Depends(netbox_settings)]
):
    return {
        "config": config,
        "status": status
    }