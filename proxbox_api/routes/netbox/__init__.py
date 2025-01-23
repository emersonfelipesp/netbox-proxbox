from fastapi import APIRouter, Depends, Query, HTTPException
from sqlmodel import select

from typing import Annotated, Any
from proxbox_api.routes.proxbox import netbox_settings
from proxbox_api.session.netbox import NetboxSessionDep
from proxbox_api.database import SessionDep, NetBoxEndpoint
# FastAPI Router
router = APIRouter()

#
# Endpoints: /netbox/<endpoint>
#

@router.post('/endpoint')
def create_netbox_endpoint(netbox: NetBoxEndpoint, session: SessionDep) -> NetBoxEndpoint:
    session.add(netbox)
    session.commit()
    session.refresh(netbox)
    return netbox

@router.get('/endpoint')
def get_netbox_endpoints(
    session: SessionDep,
    offset: int = 0,
    limit: Annotated[int, Query(le=100)] = 100
) -> list[NetBoxEndpoint]:
    netbox_endpoints = session.exec(select(NetBoxEndpoint).offset(offset).limit(limit)).all()
    return netbox_endpoints

@router.get('/endpoint/{netbox_id}')
def get_netbox_endpoint(netbox_id: int, session: SessionDep) -> NetBoxEndpoint:
    netbox_endpoint = session.get(NetBoxEndpoint, netbox_id)
    if not netbox_endpoint:
        raise HTTPException(status_code=404, detail="Netbox Endpoint not found")
    return netbox_endpoint

@router.delete('/endpoint/{netbox_id}')
def delete_netbox_endpoint(netbox_id: int, session: SessionDep) -> dict:
    netbox_endpoint = session.get(NetBoxEndpoint, netbox_id)
    if not netbox_endpoint:
        raise HTTPException(status_code=404, detail='NetBox Endpoint not found.')
    session.delete(netbox_endpoint)
    session.commit()
    return {'message': 'NetBox Endpoint deleted.'}


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



