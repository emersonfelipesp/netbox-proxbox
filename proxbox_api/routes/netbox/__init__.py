from fastapi import APIRouter, Depends

from typing import Annotated, Any

from proxbox_api.routes.proxbox import netbox_settings
from proxbox_api.session.netbox import NetboxSessionDep

# FastAPI Router
router = APIRouter()

#
# Endpoints: /netbox/<endpoint>
#
@router.get("/status")
async def netbox_status(
    nb: NetboxSessionDep
):
    """
    ### Asynchronously retrieves the status of the Netbox session.
    
    
    **Args:**
    - **nb (NetboxSessionDep):** The Netbox session dependency.
    

    **Returns:**
    - The status of the Netbox session.
    """
    
    return nb.session.status()

@router.get("/devices")
async def netbox_devices(nb: NetboxSessionDep):
    """
    ### Fetches all device roles from the Netbox session and returns them as a list.
    
    **Args:**
    - **nb (NetboxSessionDep):** The Netbox session dependency.
        
    
    **Returns:**
    - **list:** A list of device roles fetched from the Netbox session.
    """
    
    raw_list = []
    
    device_list = nb.session.dcim.device_roles.all()
    for device in device_list:
        raw_list.append(device)
    
    return raw_list

@router.get("/openapi")
async def netbox_openapi(nb: NetboxSessionDep):
    """
    ### Fetches the OpenAPI documentation from the Netbox session.
    
    **Args:**
    - **nb (NetboxSessionDep):** The Netbox session dependency.
    
    **Returns:**
    - **dict:** The OpenAPI documentation retrieved from the Netbox session.
    """
    
    
    output = nb.session.openapi()
    return output

@router.get("/")
async def netbox(
    status: Annotated[Any, Depends(netbox_status)],
    config: Annotated[Any, Depends(netbox_settings)],
    nb: NetboxSessionDep,
):
    """
    ### Asynchronous function to retrieve Netbox configuration, status, and Proxbox tag.
    
    **Parameters:**
    - **status (Annotated[Any, Depends(netbox_status)]):** The status of the Netbox instance.
    - **config (Annotated[Any, Depends(netbox_settings)]):** The configuration settings of the Netbox instance.
    - **nb (NetboxSessionDep):** The Netbox session dependency which includes the Proxbox tag.
    
    **Returns:**
        **dict:** A dictionary containing the Netbox configuration, status, and Proxbox tag.
    """

    return {
        "config": config,
        "status": status,
        "proxbox_tag": nb.tag
    }



