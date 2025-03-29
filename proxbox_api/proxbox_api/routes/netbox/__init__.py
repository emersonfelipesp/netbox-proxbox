from fastapi import APIRouter, Depends, Query, HTTPException, Depends
from sqlmodel import select

from typing import Annotated, Any

from pynetbox_api.database import SessionDep, NetBoxEndpoint
from pynetbox_api.session import RawNetBoxSession
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

GetNetBoxEndpoint = Annotated[list[NetBoxEndpoint], Depends(get_netbox_endpoints)]

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
async def netbox_status():
    """
    ### Asynchronously retrieves the status of the Netbox session.
    
    
    **Args:**
    - **nb (NetboxSessionDep):** The Netbox session dependency.
    

    **Returns:**
    - The status of the Netbox session.
    """
    nb = RawNetBoxSession
    return nb.status()


@router.get("/openapi")
async def netbox_openapi():
    """
    ### Fetches the OpenAPI documentation from the Netbox session.
    
    **Args:**
    - **nb (NetboxSessionDep):** The Netbox session dependency.
    
    **Returns:**
    - **dict:** The OpenAPI documentation retrieved from the Netbox session.
    """
    
    nb = RawNetBoxSession
    output = nb.openapi()
    return output



