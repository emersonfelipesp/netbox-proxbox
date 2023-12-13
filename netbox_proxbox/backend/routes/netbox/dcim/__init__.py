from fastapi import APIRouter, Depends

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
    default: CreateDefaultBool = False,
    data: SitesSchema = None
):
    """
    **default:** Boolean to define if Proxbox should create a default Site if there's no Site registered on Netbox.\n
    **data:** JSON to create the Site on Netbox. You can create any Site you want, like a proxy to Netbox API.
    """
    return await site.post(default, data)
