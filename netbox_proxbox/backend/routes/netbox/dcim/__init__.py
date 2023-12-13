from fastapi import APIRouter, Depends, Body

from typing import Annotated

from .sites import Sites

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
    site: Sites = Depends() 
):
    return await site.get()
    
@router.post("/sites")
async def create_sites(
    site: Sites = Depends(),
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
