from fastapi import APIRouter, Depends, Body

from typing import Annotated

from .sites import Site
from .devices import Device
from .device_types import DeviceType
from .device_roles import DeviceRole
from .manufacturers import Manufacturer

from netbox_proxbox.backend.schemas.netbox.dcim import SitesSchema

# FastAPI Router
router = APIRouter()

#
# /sites routes
#
@router.get("/sites")
async def get_sites(
    site: Site = Depends() 
):
    """
    ### Asynchronously retrieves site information.
    
    This function depends on the `Site` dependency to obtain site details and 
    returns the result of the `get` method called on the `site` object.
    
    **Args:**
    - **site (Site):** The site dependency that provides the site details.
    
    **Returns:**
    - The result of the `get` method called on the `site` object.
    """
    
    return await site.get()
    
@router.post("/sites")
async def create_sites(
    site: Site = Depends(),
    data: Annotated[SitesSchema, Body()] = None
):
    """
    ### Asynchronously creates sites using the provided site dependency and data schema.
    **Args:**
    - **site (Site):** The site dependency, injected by FastAPI's Depends.
    - **data (`Annotated[SitesSchema, Body()], optional`):** The data schema for the site, provided in the request body. Defaults to None.
    
    **Returns:**
    - The result of the `site.post()` method, which is awaited.
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
    """
    ### Asynchronous function to retrieve devices.

    This function uses dependency injection to get a `Device` instance and 
    returns the result of the `get` method called on that instance.

    **Args:**
    - **device (Device):** The device instance, injected via dependency injection.

    **Returns:**
    - The result of the `get` method called on the `device` instance.
    """


    return await device.get()


@router.post("/devices")
async def create_devices(
    device: Device = Depends(),
    data: Annotated[dict, Body()] = None
):
    """
    ### Asynchronously creates devices using the provided device and data.

    **Args:**
    - **device (Device):** The device dependency to be used for creating the device.
    - **data (dict, optional):** The data to be used for creating the device. Defaults to None.

    **Returns:**
    - **The result of the device post operation.
    """
    
    return await device.post(data)


@router.get("/manufacturers")
async def get_manufacturers(
    manufacturer: Manufacturer = Depends() 
):
    """
    ### Asynchronously retrieves a list of manufacturers.
    
    **Args:**
    - **manufacturer (Manufacturer):** Dependency injection of the Manufacturer instance.
    
    **Returns:**
    - **list:** A list of manufacturers retrieved from the database.
    """
    
    return await manufacturer.get()


@router.post("/manufacturers")
async def create_manufacturers(
    manufacturer: Manufacturer = Depends(),
    data: Annotated[dict, Body()] = None
):
    """
    ### Asynchronously creates manufacturers using the provided data.

    **Args:**
    - **manufacturer (Manufacturer):** The manufacturer dependency.
    - **data (dict, optional):** The data to be used for creating the manufacturer.

    **Returns:**
    - The result of the manufacturer's post method.
    """

    return await manufacturer.post(data)


"""
DEVICE TYPES 
"""

@router.get("/device-types")
async def get_device_types(
    device_type: DeviceType = Depends()
):
    """
    ### Asynchronous function to retrieve device types.
    
    This function uses dependency injection to get an instance of `DeviceType`
    and returns the result of the `get` method called on that instance.
    
    **Args:**
    - **device_type (DeviceType):** An instance of `DeviceType` provided by dependency injection.
    
    **Returns:**
    - The result of the `get` method called on the `device_type` instance.
    """
    
    return await device_type.get()



@router.post("/device-types")
async def create_device_types(
    device_type: DeviceType = Depends(),
    data: Annotated[dict, Body()] = None
):
    """
    ### Asynchronously creates device types.
    
    This function handles the creation of device types by accepting a `DeviceType` dependency and a dictionary of data.
    It then calls the `post` method on the `device_type` with the provided data.
    
    **Args:**
    - **device_type (DeviceType):** The device type dependency.
    - **data (dict, optional):** The data to be used for creating the device type. Defaults to None.
    
    **Returns:**
    - The result of the `post` method called on the `device_type` with the provided data.
    """
    
    return await device_type.post(data)


"""
DEVICE ROLES
"""

@router.get("/device-roles")
async def get_device_roles(
    device_role: DeviceRole = Depends()
):
    """
    ### Asynchronously retrieves device roles.
    
    **Args:**
    - **device_role (`DeviceRole` optional):** Dependency injection of the `DeviceRole` instance.
    
    **Returns:**
    - **list:** A list of device roles retrieved by the `DeviceRole` instance.
    """
    
    return await device_role.get()


@router.post("/device-roles")
async def create_device_roles(
    device_role: DeviceRole = Depends(),
    data: Annotated[dict, Body()] = None
):
    """
    ### Asynchronously creates device roles.
    
    This function handles the creation of device roles by accepting a device role dependency and a data dictionary.
    It then posts the data to the device role.
    
    **Args:**
    - **device_role (`DeviceRole`):** The device role dependency.
    - **data (dict, optional):** The data dictionary to be posted. Defaults to None.
    
    **Returns:**
    - The result of the device role post operation.
    """
    
    return await device_role.post(data)