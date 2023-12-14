from fastapi import APIRouter, Depends, Body

from typing import Annotated

from .sites import Site
from .devices import Device
from .device_types import DeviceType
from .device_roles import DeviceRole
from .manufacturers import Manufacturer

from netbox_proxbox.backend.schemas.netbox import CreateDefaultBool
from netbox_proxbox.backend.schemas.netbox.dcim import SitesSchema

from netbox_proxbox.backend.logging import logger

# FastAPI Router
router = APIRouter()

#
# /sites routes
#
@router.get("/sites")
async def get_sites(
    site: Site = Depends() 
):
    return await site.get()
    
@router.post("/sites")
async def create_sites(
    site: Site = Depends(),
    data: Annotated[SitesSchema, Body()] = None
):
    """
    **default:** Boolean to define if Proxbox should create a default Site if there's no Site registered on Netbox.\n
    **data:** JSON to create the Site on Netbox. You can create any Site you want, like a proxy to Netbox API.
    """


    # if default:
    #     print(type(default))
    #     print(default)
    #     return await site(default=True).post()

    if data:
        return await site.post(data)
    
    return await site.post()

#
# /devices routes
#
@router.get("/devices")
async def get_devices(
    device: Device = Depends() 
):
    return await device.get()

@router.get("/manufacturers")
async def get_manufacturers(
    manufacturer: Manufacturer = Depends() 
):
    return await manufacturer.get()

@router.get("/device-types")
async def get_device_types(
    device_type: DeviceType = Depends()
):
    return await device_type.get()

@router.get("/device-roles")
async def get_device_roles(
    device_role: DeviceRole = Depends()
):
    return await device_role.get()