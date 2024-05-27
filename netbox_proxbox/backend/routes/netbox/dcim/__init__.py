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

@router.post("/devices")
async def create_devices(
    device: Device = Depends(),
    data: Annotated[dict, Body()] = None
):
    """
    **default:** Boolean to define if Proxbox should create a default Device if there's no Device registered on Netbox.\n
    **data:** JSON to create the Device on Netbox. You can create any Device you want, like a proxy to Netbox API.
    """

    return await device.post(data)

@router.get("/manufacturers")
async def get_manufacturers(
    manufacturer: Manufacturer = Depends() 
):
    return await manufacturer.get()

@router.post("/manufacturers")
async def create_manufacturers(
    manufacturer: Manufacturer = Depends(),
    data: Annotated[dict, Body()] = None
):
    """
    **default:** Boolean to define if Proxbox should create a default Manufacturer if there's no Manufacturer registered on Netbox.\n
    **data:** JSON to create the Manufacturer on Netbox. You can create any Manufacturer you want, like a proxy to Netbox API.
    """

    return await manufacturer.post(data)



"""
DEVICE TYPES 
"""

@router.get("/device-types")
async def get_device_types(
    device_type: DeviceType = Depends()
):
    return await device_type.get()

@router.post("/device-types")
async def create_device_types(
    device_type: DeviceType = Depends(),
    data: Annotated[dict, Body()] = None
):
    return await device_type.post(data)


"""
DEVICE ROLES
"""

@router.get("/device-roles")
async def get_device_roles(
    device_role: DeviceRole = Depends()
):
    return await device_role.get()


@router.post("/device-roles")
async def create_device_roles(
    device_role: DeviceRole = Depends(),
    data: Annotated[dict, Body()] = None
):
    return await device_role.post(data)